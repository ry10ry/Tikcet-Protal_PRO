import json
import uuid
from datetime import datetime
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.main import app,engine,Ticket,Attachment,Entry
from app.changes import ChangeRequest,CRHistory,CRFile
from app.services import ServiceRequest,SRHistory,SRFile
from app.archive import ArchiveRecord,ArchiveFile,MARKER
from test_services import H,login,PNG
from test_z_changes import uploads
import base64


def test_complete_offline_archives_verified_cleanup_and_reports(tmp_path,monkeypatch):
 root=tmp_path/'MOMCC_Archive';root.mkdir();(root/MARKER).write_text(str(uuid.uuid4()))
 monkeypatch.setenv('ARCHIVE_ROOT',str(root));monkeypatch.setenv('ARCHIVE_PURGE_ENABLED','false')
 old=datetime(2024,1,1,12)
 with TestClient(app) as admin,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  cfg=admin.get('/api/settings').json()
  fault=requester.post('/api/tickets',json=dict(title='Offline historical fault',description='Full fault content',category=cfg['categories'][0],domain=cfg['domains'][0],attachments=[dict(filename='Screenshot.png',data=base64.b64encode(PNG).decode())]),headers=H).json();fp='/api/tickets/'+str(fault['id'])
  admin.post(fp+'/actions',json=dict(action='assign'),headers=H)
  admin.post(fp+'/actions',json=dict(action='resolve',text='Historical resolution'),headers=H)
  requester.post(fp+'/actions',json=dict(action='close',text='Confirmed resolved'),headers=H)
  cr=admin.post('/api/changes',json={'cr_date':'2024-01-01'},headers=H).json();cp='/api/changes/'+str(cr['id'])
  cr=admin.post(cp+'/save',json=dict(version=cr['version'],content=dict(description='Historical change',background='Reason',scope='Scope'),uploads=uploads()),headers=H).json()
  cr=admin.post(cp+'/save',json=dict(version=cr['version'],content={},uploads=[uploads()[1]]),headers=H).json()
  for action in ['submit','support','approve']:cr=admin.post(cp+'/actions',json=dict(version=cr['version'],action=action),headers=H).json()
  email=b'From: approval@example.com\r\nSubject: Approved\r\n\r\nApproved.'
  cr=admin.post(cp+'/istd-evidence',json=dict(version=cr['version'],filename='Approval.eml',data=base64.b64encode(email).decode()),headers=H).json()
  cr=admin.post(cp+'/actions',json=dict(version=cr['version'],action='close'),headers=H).json()
  sr=admin.post('/api/services',json={'sr_date':'2024-01-01'},headers=H).json();sp='/api/services/'+str(sr['id'])
  sr=admin.post(sp+'/save',json=dict(version=sr['version'],subject='Historical service',description='Service description',uploads=[dict(filename='Screenshot.png',data=base64.b64encode(PNG).decode()),dict(filename='old.txt',data=base64.b64encode(b'Historical removed file').decode())]),headers=H).json()
  old_file=next(f['id'] for f in sr['files'] if f['filename']=='old.txt')
  sr=admin.post(sp+'/save',json=dict(version=sr['version'],subject='Historical service',description='Service description',remove_file_ids=[old_file]),headers=H).json()
  for action in ['submit','approve']:sr=admin.post(sp+'/actions',json=dict(version=sr['version'],action=action),headers=H).json()
  with Session(engine) as s:
   f=s.get(Ticket,fault['id']);f.created_at=old;f.closed_at=old;f.updated_at=old
   c=s.get(ChangeRequest,cr['id']);c.created_at=old
   r=s.get(ServiceRequest,sr['id']);r.created_at=old
   for model,key,id in [(Entry,Entry.ticket_id,f.id),(CRHistory,CRHistory.cr_id,c.id),(SRHistory,SRHistory.sr_id,r.id)]:
    for h in s.scalars(select(model).where(key==id)):h.created_at=old
   import app.main as main
   attachment=s.scalar(select(Attachment).where(Attachment.ticket_id==f.id));file_id=attachment.id;source=main.UPLOAD_DIR/attachment.storage_name
   s.commit()
  assert requester.get('/api/archive/status').status_code==403
  assert requester.post('/api/archive/run',json={},headers=H).status_code==403
  assert admin.get('/api/archive/status').json()['eligible']==3
  for _ in range(3):
   response=admin.post('/api/archive/run',json={},headers=H);assert response.status_code==200,response.text
   assert response.json()['item']['state']=='copied'
  assert admin.post('/api/archive/run',json={},headers=H).json()['item'] is None
  assert (root/'index.html').is_file() and (root/'archive.csv').is_file()
  with Session(engine) as s:
   rows=s.scalars(select(ArchiveRecord)).all();assert len(rows)==3
   for row in rows:
    data=json.loads((root/row.folder/'record.json').read_text())
    assert data['history'] and data['attachments']
    if row.kind=='CR':assert len(data['attachments'])==5
    if row.kind=='SR':assert any(not f['active'] for f in data['attachments'])
    assert (root/row.folder/'manifest.json').is_file()
   meta=s.scalar(select(ArchiveFile).where(ArchiveFile.kind=='FAULT',ArchiveFile.file_id==file_id))
   copied=root/s.get(ArchiveRecord,meta.archive_id).folder/meta.path
   assert copied.read_bytes()==PNG and source.is_file()
  assert admin.post('/api/archive/purge',json={},headers=H).status_code==409
  monkeypatch.setenv('ARCHIVE_PURGE_ENABLED','true')
  copied.write_bytes(b'corrupt')
  assert admin.post('/api/archive/purge',json={},headers=H).status_code==409
  assert source.read_bytes()==PNG
  copied.write_bytes(PNG)
  original_unlink=Path.unlink
  def deny_source(path,*args,**kwargs):
   if path==source:raise PermissionError('Simulated source file lock')
   return original_unlink(path,*args,**kwargs)
  with monkeypatch.context() as blocked:
   blocked.setattr(Path,'unlink',deny_source)
   assert admin.post('/api/archive/purge',json={},headers=H).status_code==503
   assert source.is_file()
   with Session(engine) as s:assert s.scalar(select(ArchiveRecord).where(ArchiveRecord.kind=='FAULT')).state=='copied'
  for _ in range(3):assert admin.post('/api/archive/purge',json={},headers=H).status_code==200
  assert not source.exists()
  with Session(engine) as s:
   assert all(not f.data for f in s.scalars(select(CRFile).where(CRFile.cr_id==cr['id'])))
   assert all(not f.data for f in s.scalars(select(SRFile).where(SRFile.sr_id==sr['id'])))
  assert requester.get('/api/attachments/'+str(file_id)).content==PNG
  assert admin.get(cp+'/documents/runbook').content==base64.b64decode(uploads()[1]['data'])
  assert admin.get(cp+'/istd-email').status_code==200
  assert admin.get(sp+'/customer-email').status_code==200
  assert requester.get(fp).json()['archive_state']=='archived'
  assert admin.post(cp+'/actions',json=dict(version=cr['version'],action='comment',reason='Change'),headers=H).status_code==409
  assert admin.post(sp+'/actions',json=dict(version=sr['version'],action='comment',comment='Change'),headers=H).status_code==409
  assert admin.post(fp+'/delete',json={},headers=H).status_code==409
  for endpoint in ['/api/report','/api/internal/reports/cr','/api/internal/reports/sr']:
   report=admin.get(endpoint+'?month=2024-01');assert report.status_code==200
   assert 'Archive State' in report.text and 'archived' in report.text
  monkeypatch.setenv('ARCHIVE_ROOT',str(tmp_path/'disconnected'))
  assert admin.post('/api/archive/run',json={},headers=H).status_code==503
  assert admin.get('/api/attachments/'+str(file_id)).status_code==503
  assert admin.get('/api/tickets').status_code==200
  assert admin.get('/api/changes').status_code==200
  assert admin.get('/api/services').status_code==200
  assert admin.get('/api/report?month=2024-01').status_code==200
  # Export all types to removable storage and disconnect it. Docker keeps only
  # the local staging mount, while lookup/report metadata stays in the DB.
  import shutil
  import app.archive as archive
  monkeypatch.setenv('ARCHIVE_ROOT',str(root))
  external=tmp_path/'external';shutil.copytree(root,external)
  receipt={'target':(root/MARKER).read_text(),'location':str(external),'records':[]}
  with Session(engine) as s:
   for row in s.scalars(select(ArchiveRecord)):
    receipt['records'].append({'folder':row.folder,'manifest_sha256':archive.digest(external/row.folder/'manifest.json')})
  assert len(archive.finish_export(engine,receipt))==3
  assert archive.finish_export(engine,receipt)==[]
  shutil.rmtree(external)
  assert (root/'index.html').is_file()
  assert not list(root.glob('*/*/record.json'))
  assert requester.get(fp).json()['archive_state']=='offline'
  assert admin.get(cp).json()['archive_state']=='offline'
  assert admin.get(sp).json()['archive_state']=='offline'
  for url in ['/api/attachments/'+str(file_id),cp+'/documents/runbook',sp+'/customer-email']:
   response=admin.get(url);assert response.status_code==503
   assert 'archived offline' in response.text and str(external) in response.text
  for endpoint in ['/api/report','/api/internal/reports/cr','/api/internal/reports/sr']:
   report=admin.get(endpoint+'?month=2024-01');assert report.status_code==200
   assert 'offline' in report.text and str(external) in report.text
  assert all(r['state']=='offline' for r in admin.get('/api/archive/status').json()['records'])


def test_archive_target_required_and_calendar_year_cutoff(monkeypatch,tmp_path):
 import pytest
 from fastapi import HTTPException
 import app.archive as archive
 monkeypatch.setenv('ARCHIVE_ROOT',str(tmp_path))
 with pytest.raises(HTTPException):archive.root()
 monkeypatch.setattr(archive,'now',lambda:datetime(2024,2,29,12))
 assert archive.cutoff()==datetime(2023,2,28,12)


def test_cancelled_completed_date_active_records_and_space_guard(tmp_path,monkeypatch):
 import app.archive as archive
 from types import SimpleNamespace
 root=tmp_path/'MOMCC_Archive';root.mkdir();(root/MARKER).write_text(str(uuid.uuid4()))
 monkeypatch.setenv('ARCHIVE_ROOT',str(root))
 with TestClient(app) as admin,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  cfg=admin.get('/api/settings').json()
  def create(title):return requester.post('/api/tickets',json=dict(title=title,description='Archive retention policy',category=cfg['categories'][0],domain=cfg['domains'][0]),headers=H).json()['id']
  cancelled=create('Old cancelled');active=create('Old active');recent=create('Recently completed')
  requester.post('/api/tickets/'+str(cancelled)+'/actions',json=dict(action='cancel',text='Withdrawn'),headers=H)
  admin.post('/api/tickets/'+str(recent)+'/actions',json=dict(action='assign'),headers=H)
  admin.post('/api/tickets/'+str(recent)+'/actions',json=dict(action='resolve',text='Fixed'),headers=H)
  requester.post('/api/tickets/'+str(recent)+'/actions',json=dict(action='close',text='Verified'),headers=H)
  with Session(engine) as s:
   for id in [cancelled,active,recent]:s.get(Ticket,id).created_at=datetime(2024,1,1)
   for h in s.scalars(select(Entry).where(Entry.ticket_id==cancelled)):h.created_at=datetime(2024,1,1)
   s.commit()
  assert admin.get('/api/archive/status').json()['eligible']==1
  with monkeypatch.context() as full:
   full.setattr(archive.shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
   assert admin.post('/api/archive/run',json={},headers=H).status_code==409
   with Session(engine) as s:assert s.scalar(select(ArchiveRecord).where(ArchiveRecord.kind=='FAULT',ArchiveRecord.record_id==cancelled)) is None
  assert admin.post('/api/archive/run',json={},headers=H).status_code==200
  assert admin.post('/api/archive/run',json={},headers=H).json()['item'] is None
  assert admin.get('/api/tickets/'+str(active)).json()['status']=='New'
  assert admin.get('/api/tickets/'+str(recent)).json()['archive_state']==''


def test_offline_receipt_mismatch_preserves_online_source(tmp_path,monkeypatch):
 import pytest
 from fastapi import HTTPException
 import app.archive as archive
 root=tmp_path/'stage';root.mkdir();(root/MARKER).write_text(str(uuid.uuid4()))
 monkeypatch.setenv('ARCHIVE_ROOT',str(root))
 with TestClient(app) as admin:
  login(admin,'admin@example.com')
  cfg=admin.get('/api/settings').json()
  fault=admin.post('/api/tickets',json=dict(title='Transfer verification',description='Must retain source on failure',category=cfg['categories'][0],domain=cfg['domains'][0],attachments=[dict(filename='Screenshot.png',data=base64.b64encode(PNG).decode())]),headers=H).json()
  id=fault['id'];admin.post(f'/api/tickets/{id}/actions',json=dict(action='cancel',text='Withdrawn'),headers=H)
  with Session(engine) as s:
   for h in s.scalars(select(Entry).where(Entry.ticket_id==id)):h.created_at=datetime(2024,1,1)
   s.commit()
  item=archive.archive_one(engine)
  receipt={'target':(root/MARKER).read_text(),'location':'E:/MOMCC_Archive','records':[{'folder':item['folder'],'manifest_sha256':'0'*64}]}
  with pytest.raises(HTTPException):archive.finish_export(engine,receipt)
  assert admin.get(f'/api/tickets/{id}').json()['archive_state']=='copied'
  with Session(engine) as s:
   file=s.scalar(select(Attachment).where(Attachment.ticket_id==id));assert (archive.upload_dir()/file.storage_name).exists()
  receipt['records'][0]['manifest_sha256']=archive.digest(root/item['folder']/'manifest.json')
  # Explicit verified export cleans online files without globally enabling purge.
  archive.finish_export(engine,receipt)
  with Session(engine) as s:assert not (archive.upload_dir()/file.storage_name).exists()
  assert admin.get(f'/api/tickets/{id}').json()['archive_state']=='offline'
