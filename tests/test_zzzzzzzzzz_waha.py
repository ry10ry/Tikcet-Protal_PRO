import os
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.main import app,engine,now
from app.waha import WhatsAppOutbox,WhatsAppAssignmentOutbox,process_outbox
from test_services import H,login


def test_waha_fault_transaction_delivery_retry_and_delete(monkeypatch):
 import app.waha as waha
 monkeypatch.setenv('WAHA_ENABLED','true');monkeypatch.setenv('WAHA_URL','http://waha.test:3000')
 monkeypatch.setenv('WAHA_API_KEY','test-key-never-use-in-production')
 monkeypatch.setenv('WAHA_SESSION','default');monkeypatch.setenv('WAHA_GROUP_CHAT_ID','123456@g.us')
 monkeypatch.setenv('PORTAL_URL','https://portal.test')
 with TestClient(app) as admin,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  config=admin.get('/api/settings').json()
  body=dict(title='New WhatsApp fault',description='Test issue description',category=config['categories'][0],domain=config['domains'][0])
  # Invalid attachments must roll back the ticket and its queue item together.
  bad=admin.post('/api/tickets',json={**body,'attachments':[dict(filename='bad.txt',data='invalid base64!')]},headers=H)
  assert bad.status_code==422
  with Session(engine) as s:assert s.scalar(select(func.count()).select_from(WhatsAppOutbox))==0
  response=requester.post('/api/tickets',json=body,headers=H);assert response.status_code==200
  id=response.json()['id'];p='/api/tickets/'+str(id)
  with Session(engine) as s:
   row=s.scalar(select(WhatsAppOutbox));queue_id=row.id
   assert row.status=='pending' and row.chat_id=='123456@g.us'
   assert 'New Fault Ticket' in row.text and f'MOMCC-{id:06d}' in row.text and 'https://portal.test' not in row.text
   assert len(row.text.splitlines())==7 and 'Test issue description' not in row.text
  admin.post(p+'/actions',json=dict(action='assign'),headers=H)
  requester.post(p+'/actions',json=dict(action='note',text='Additional details'),headers=H)
  admin.post(p+'/actions',json=dict(action='vendor',text='Vendor investigation'),headers=H)
  admin.post('/api/services',json={'sr_date':'2026-10-16'},headers=H)
  admin.post('/api/changes',json={'cr_date':'2026-10-16'},headers=H)
  with Session(engine) as s:assert s.scalar(select(func.count()).select_from(WhatsAppOutbox))==1
  calls=[]
  def fail(*args):calls.append(args);raise OSError('failure')
  monkeypatch.setattr(waha,'send_text',fail)
  # MySQL DATETIME may round the initial timestamp to the next second.
  # Make this delivery explicitly due rather than depending on test speed.
  with Session(engine) as s:
   s.get(WhatsAppOutbox,queue_id).next_attempt_at=now()-timedelta(seconds=1);s.commit()
  assert process_outbox(engine)==2
  with Session(engine) as s:
   row=s.get(WhatsAppOutbox,queue_id)
   assert row.status=='pending' and row.attempts==1 and row.next_attempt_at>now()
   assert row.last_error=='WAHA connection failed or timed out' and 'test-key' not in row.last_error
  assert process_outbox(engine)==0
  with Session(engine) as s:
   s.get(WhatsAppOutbox,queue_id).next_attempt_at=now()-timedelta(seconds=1);s.commit()
  monkeypatch.setattr(waha,'send_text',lambda *args:calls.append(args))
  assert process_outbox(engine)==1 and process_outbox(engine)==0
  with Session(engine) as s:assert s.get(WhatsAppOutbox,queue_id).status=='sent'
  assert calls[-1][2:4]==('default','123456@g.us')
  assert admin.post('/api/tickets/'+str(id)+'/delete',json={},headers=H).status_code==200
  with Session(engine) as s:assert s.get(WhatsAppOutbox,queue_id) is None
  # Disabling the integration makes new tickets portal-only.
  monkeypatch.setenv('WAHA_ENABLED','false')
  assert requester.post('/api/tickets',json=body,headers=H).status_code==200
  with Session(engine) as s:assert s.scalar(select(func.count()).select_from(WhatsAppOutbox))==0


def test_waha_http_payload_and_acknowledgement(monkeypatch):
 import json
 import app.waha as waha
 calls=[]
 class Response:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def read(self,n):return b'{"id":"message-id"}'
 def request(req,timeout):calls.append((req,timeout));return Response()
 monkeypatch.setattr(waha,'urlopen',request)
 waha.send_text('http://waha.test:3000/','fake-key','default','123@g.us','New Fault Ticket')
 req,timeout=calls[0]
 assert req.full_url=='http://waha.test:3000/api/sendText' and timeout==10
 assert req.get_header('X-api-key')=='fake-key'
 assert json.loads(req.data)==dict(session='default',chatId='123@g.us',text='New Fault Ticket',linkPreview=False)


def test_assignment_notification_transaction_group_reassignment_and_disabled(monkeypatch):
 import app.waha as waha
 monkeypatch.setenv('WAHA_ENABLED','false')
 with TestClient(app) as admin,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  config=admin.get('/api/settings').json()
  body=dict(title='Assign notification',description='Issue',category=config['categories'][0],domain=config['domains'][0])
  ticket=requester.post('/api/tickets',json=body,headers=H).json()
  p='/api/tickets/'+str(ticket['id'])
  monkeypatch.setenv('WAHA_ENABLED','true')
  monkeypatch.setenv('WAHA_GROUP_CHAT_ID','123456@g.us')
  monkeypatch.setenv('WAHA_SESSION','existing-session')
  monkeypatch.setenv('WAHA_URL','http://waha.test:3000')
  monkeypatch.setenv('WAHA_API_KEY','test-key-never-use-in-production')
  def rows():
   with Session(engine) as s:return s.scalars(select(WhatsAppAssignmentOutbox).where(WhatsAppAssignmentOutbox.ticket_id==ticket['id'])).all()
  assert requester.post(p+'/actions',json={'action':'assign'},headers=H).status_code==403
  assert admin.post(p+'/actions',json={'action':'assign','assignee_id':999999},headers=H).status_code==422
  assert admin.post(p+'/actions',json={'action':'assign','severity':'not-a-severity'},headers=H).status_code==422
  assert admin.post(p+'/actions',json={'action':'assign','attachments':[{'filename':'bad.txt','data':'!'}]},headers=H).status_code==422
  assert not rows()
  assert admin.post(p+'/actions',json={'action':'assign'},headers=H).status_code==200
  row=rows()[0]
  assert row.text=='\n'.join(['Fault Ticket Assigned',f"Number: MOMCC-{ticket['id']:06d}",'Subject: Assign notification','Engineer: ServiceDesk Administrator'])
  assert (row.chat_id,row.session_name)==('123456@g.us','existing-session')
  calls=[]
  monkeypatch.setattr(waha,'send_text',lambda *args:calls.append(args))
  with Session(engine) as s:
   s.get(WhatsAppAssignmentOutbox,row.id).next_attempt_at=now()-timedelta(seconds=1);s.commit()
  assert process_outbox(engine)==1 and process_outbox(engine)==0
  assert calls[0][2:]==('existing-session','123456@g.us',row.text)
  # Every successful assign action, including assigning the same Engineer again, is an event.
  engineer=next(u for u in admin.get('/api/users').json() if u['email']=='infra@example.com')
  for _ in range(2):
   assert admin.post(p+'/actions',json={'action':'assign','assignee_id':engineer['id']},headers=H).status_code==200
  assert len(rows())==3 and all('Engineer: '+engineer['name'] in r.text for r in rows()[1:])
  monkeypatch.setenv('WAHA_ENABLED','false')
  assert admin.post(p+'/actions',json={'action':'assign'},headers=H).status_code==200
  assert len(rows())==3
  assert admin.post(p+'/delete',json={},headers=H).status_code==200
  assert not rows()
