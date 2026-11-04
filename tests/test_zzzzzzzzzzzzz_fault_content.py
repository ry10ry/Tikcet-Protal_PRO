import base64
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app,engine,Notification
from test_services import H,login,PNG


def test_visibility_rich_tables_and_private_attachments():
 with TestClient(app) as admin,TestClient(app) as requester,TestClient(app) as infra:
  login(admin,'admin@example.com');login(requester,'tm@example.com');login(infra,'infra@example.com')
  cfg=admin.get('/api/settings').json()
  body=dict(title='Internal table fault',description='fallback description',category=cfg['categories'][0],domain=cfg['domains'][0],attachments=[dict(filename='private.png',data=base64.b64encode(PNG).decode())],description_html='<table onclick="alert(1)"><tr><th>Host</th><th>Status</th></tr><tr><td rowspan="2">SERVER1</td><td>Failed<script>alert(1)</script><img src="https://evil.test/x" onerror="alert(1)"></td></tr></table>')
  response=infra.post('/api/tickets',json=body,headers=H);assert response.status_code==200,response.text
  ticket=response.json();id=ticket['id'];assert ticket['visibility']=='Internal'
  assert '<table>' in ticket['description_html'] and 'rowspan="2"' in ticket['description_html']
  assert all(x not in ticket['description_html'] for x in ['onclick','script','img','evil.test'])
  assert 'SERVER1' in ticket['description'] and '\t' in ticket['description']
  detail=infra.get(f'/api/tickets/{id}').json();attachment=detail['attachments'][0]['id']
  assert admin.get(f'/api/tickets/{id}').status_code==200
  assert requester.get(f'/api/tickets/{id}').status_code==404
  assert requester.get(f'/api/attachments/{attachment}').status_code==404
  assert requester.post(f'/api/tickets/{id}/actions',json=dict(action='note',text='Attempt private update'),headers=H).status_code==404
  assert id not in [r['id'] for r in requester.get('/api/tickets').json()]
  # Even an accidentally addressed requester notification cannot reveal it.
  requester_id=requester.get('/api/me').json()['id']
  with Session(engine) as s:
   s.add(Notification(user_id=requester_id,ticket_id=id,text='Private title'));s.commit()
  assert id not in [n['ticket_id'] for n in requester.get('/api/notifications').json()]
  public=infra.post('/api/tickets',json={**body,'visibility':'Public'},headers=H).json()
  assert requester.get('/api/tickets/'+str(public['id'])).status_code==200
  assert requester.post('/api/tickets',json={**body,'visibility':'Internal'},headers=H).status_code==403
  assert requester.post('/api/tickets',json=body,headers=H).status_code==403
  own=requester.post('/api/tickets',json={**body,'attachments':[]},headers=H).json();assert own['visibility']=='Public'
  assert admin.post(f'/api/tickets/{id}/delete',json={},headers=H).status_code==200


def test_shared_requester_reply_preserves_owner_workflow_and_private_boundary():
 with TestClient(app) as admin,TestClient(app) as owner,TestClient(app) as peer:
  login(admin,'admin@example.com');login(owner,'tm@example.com');login(peer,'other@example.com')
  cfg=admin.get('/api/settings').json()
  body=dict(title='Shared requester conversation',description='Public issue',category=cfg['categories'][0],domain=cfg['domains'][0])
  before=len(owner.get('/api/tickets').json())
  assert owner.post('/api/tickets',json={**body,'attachments':[dict(filename='file.txt',data=base64.b64encode(b'data').decode())]},headers=H).status_code==403
  assert len(owner.get('/api/tickets').json())==before
  ticket=owner.post('/api/tickets',json=body,headers=H).json();p='/api/tickets/'+str(ticket['id'])
  assert admin.post(p+'/actions',json=dict(action='information',text='Need owner confirmation'),headers=H).status_code==200
  reply=peer.post(p+'/actions',json=dict(action='note',text='I have the same issue',attachments=[dict(filename='reply.txt',data=base64.b64encode(b'peer evidence').decode())]),headers=H)
  assert reply.status_code==200 and reply.json()['status']=='Additional Information Requested'
  detail=owner.get(p).json()
  assert any(e['text']=='I have the same issue' and e['author']=='other@example.com' for e in detail['entries'])
  assert peer.get('/api/attachments/'+str(detail['attachments'][0]['id'])).content==b'peer evidence'
  for action in ['cancel','close','assign']:
   assert peer.post(p+'/actions',json=dict(action=action,text='Not owner'),headers=H).status_code==403
  assert owner.post(p+'/actions',json=dict(action='note',text='Owner response'),headers=H).json()['status']=='In Progress'
  assert admin.post(p+'/actions',json=dict(action='resolve',text='Fixed'),headers=H).status_code==200
  assert peer.post(p+'/actions',json=dict(action='note',text='Thank you'),headers=H).json()['status']=='Resolved, Pending Confirmation'
  assert owner.post(p+'/actions',json=dict(action='close',text='Verified'),headers=H).status_code==200
  assert peer.post(p+'/actions',json=dict(action='note',text='After close'),headers=H).status_code==409
  private=admin.post('/api/tickets',json={**body,'visibility':'Internal'},headers=H).json()
  assert peer.post('/api/tickets/'+str(private['id'])+'/actions',json=dict(action='note',text='Private attempt'),headers=H).status_code==404
