import os
import tempfile
from datetime import timedelta

# Set TEST_DATABASE_URL to a disposable MySQL database for real-DB tests.
os.environ['DATABASE_URL'] = os.environ.get('TEST_DATABASE_URL','sqlite:///'+tempfile.mktemp(suffix='.db'))
os.environ['ADMIN_EMAIL']='admin@example.com'
os.environ['ADMIN_PASSWORD']='TestPassword123!'
os.environ['COOKIE_SECURE']='false'
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app, engine, Ticket, now, auto_close

headers={'X-Requested-With':'ServiceDesk'}
def post(client,path,body):
    return client.post('/api'+path,json=body,headers=headers)
def login(client,email):
    assert post(client,'/login',{'email':email,'password':'TestPassword123!'}).status_code==200

def test_workflow_and_permissions():
    with TestClient(app) as admin, TestClient(app) as requester, TestClient(app) as other:
        login(admin,'admin@example.com')
        for email,role in [('tm@example.com','requester'),('other@example.com','requester'),('infra@example.com','infra')]:
            assert post(admin,'/users',{'name':email,'email':email,'password':'TestPassword123!','role':role}).status_code==200
        login(requester,'tm@example.com');login(other,'other@example.com')
        body={'title':'Agent audio issue','description':'Agent cannot hear customer','category':'Amazon Connect','location':'MOMCC','domain':'UAT','severity':'High'}
        r=post(requester,'/tickets',body);assert r.status_code==200
        tid=r.json()['id'];path=f'/tickets/{tid}/actions'
        assert other.get(f'/api/tickets/{tid}').status_code==200
        assert any(t['id']==tid for t in other.get('/api/tickets').json())
        assert post(other,path,{'action':'note','text':'Unauthorized edit'}).status_code==403
        assert post(requester,path,{'action':'assign'}).status_code==403
        assert post(admin,path,{'action':'resolve','text':'Fixed'}).status_code==422
        assert post(admin,path,{'action':'assign'}).json()['status']=='In Progress'
        assert post(admin,path,{'action':'note','text':'Investigated microphone permissions','minutes':15}).status_code==200
        assert admin.get(f'/api/tickets/{tid}').json()['first_response_at']
        assert post(admin,path,{'action':'hold','text':'Awaiting endpoint team'}).status_code==403
        assert post(admin,path,{'action':'information','text':'Please provide logs'}).json()['status']=='Additional Information Requested'
        assert admin.get('/api/settings').json()['status_labels']['Additional Information Requested']=='Pending Customer'
        assert post(other,path,{'action':'note','text':'Other requester'}).status_code==403
        assert post(admin,path,{'action':'note','text':'Waiting'}).json()['status']=='Additional Information Requested'
        assert post(requester,path,{'action':'note','text':'Additional details provided'}).status_code==200
        assert requester.get(f'/api/tickets/{tid}').json()['status']=='In Progress'
        assert post(admin,path,{'action':'resume','text':'Endpoint available'}).status_code==403
        assert post(admin,path,{'action':'resolve','text':'Enabled microphone permission'}).json()['status']=='Resolved, Pending Confirmation'
        assert post(admin,path,{'action':'close','text':'Verified'}).status_code==403
        assert post(requester,path,{'action':'close'}).status_code==422
        assert post(requester,path,{'action':'close','text':'Tested successfully'}).json()['status']=='Closed'
        assert post(admin,path,{'action':'note','text':'Late edit'}).status_code==409
        with TestClient(app) as infra:
            login(infra,'infra@example.com')
            import base64
            result=post(infra,path,{'action':'note','text':'Post-close follow-up','attachments':[{'filename':'followup.txt','data':base64.b64encode(b'followup').decode()}]})
            assert result.status_code==200 and result.json()['status']=='Closed'
            detail=infra.get(f'/api/tickets/{tid}').json()
            assert any(e['text']=='Post-close follow-up' for e in detail['entries'])
            assert detail['attachments'][-1]['entry_id'] is not None
            assert post(infra,path,{'action':'note','text':'','attachments':[]}).status_code==422
            assert post(infra,path,{'action':'note','text':'Change severity','severity':'Low'}).status_code==403
            assert post(infra,path,{'action':'severity','severity':'Low'}).status_code==403
            assert post(infra,path,{'action':'assign'}).status_code==403
        assert requester.get('/api/report?month=2026-10').status_code==403
        month=now().strftime('%Y-%m')
        report=admin.get('/api/report?month='+month)
        assert report.status_code==200 and 'Enabled microphone' not in report.text
        assert 'First response minutes' not in report.text and 'Resolution minutes' not in report.text and 'Work minutes' not in report.text and 'Agent audio issue' in report.text
        assert post(admin,'/tickets',body).status_code==200
        t2=post(requester,'/tickets',body).json()['id']
        post(admin,f'/tickets/{t2}/actions',{'action':'assign'})
        post(admin,f'/tickets/{t2}/actions',{'action':'resolve','text':'Resolved'})
        with Session(engine) as s:
            t=s.get(Ticket,t2);t.resolved_at=now()-timedelta(days=3,minutes=1);s.commit()
            assert auto_close(s)==1
            assert auto_close(s)==0
        assert requester.get(f'/api/tickets/{t2}').json()['status']=='Closed'
        t3=post(requester,'/tickets',body).json()['id']
        assert post(admin,f'/tickets/{t3}/actions',{'action':'decline','text':'Not an Infra fault'}).json()['status']=='Cancelled'
        assert post(requester,'/tickets',body).status_code==200
        assert requester.post('/api/tickets',json=body).status_code==403
        assert requester.get('/api/notifications').json()
        assert post(requester,'/logout',{}).status_code==200
        assert requester.get('/api/me').status_code==401

def test_settings_attachments_users_and_singapore_report():
    import base64
    import app.main as main
    from datetime import datetime
    main.UPLOAD_DIR = __import__('pathlib').Path(tempfile.mkdtemp())
    with TestClient(app) as admin, TestClient(app) as requester, TestClient(app) as other:
        login(admin,'admin@example.com');login(requester,'tm@example.com');login(other,'other@example.com')
        config=admin.get('/api/settings').json()
        config['categories'].append('Test category')
        config['severities'].append('Urgent')
        config['status_labels']['New']='Reported'
        config['fault_templates']['Test category']='Describe the fault here'
        assert post(requester,'/settings',config).status_code==403
        assert post(admin,'/settings',config).status_code==200
        body={'title':'SGT boundary ticket','description':'Attachment test','category':'Test category','domain':'PROD','severity':'Urgent','attachments':[{'filename':'test.txt','data':base64.b64encode(b'hello attachment').decode()}]}
        result=post(requester,'/tickets',body);assert result.status_code==200
        tid=result.json()['id']
        detail=requester.get(f'/api/tickets/{tid}').json();aid=detail['attachments'][0]['id']
        assert requester.get(f'/api/attachments/{aid}').content==b'hello attachment'
        assert other.get(f'/api/attachments/{aid}').content==b'hello attachment'
        assert post(other,f'/tickets/{tid}/actions',{'action':'note','text':'Unauthorized reply'}).status_code==403
        assert TestClient(app).get(f'/api/attachments/{aid}').status_code==401
        assert post(admin,f'/tickets/{tid}/actions',{'action':'assign'}).status_code==200
        assert post(admin,f'/tickets/{tid}/actions',{'action':'note','text':'Attached diagnosis','attachments':[{'filename':'diagnosis.txt','data':base64.b64encode(b'diagnosis').decode()}]}).status_code==200
        detail=admin.get(f'/api/tickets/{tid}').json()
        assert detail['attachments'][1]['entry_id'] is not None
        bad={**body,'attachments':[{'filename':'bad.txt','data':'not base64!'}]}
        count=len(admin.get('/api/tickets').json())
        assert post(requester,'/tickets',bad).status_code==422
        assert len(admin.get('/api/tickets').json())==count
        with Session(engine) as session:
            t=session.get(Ticket,tid);t.created_at=datetime(2026,9,30,16,0);session.commit()
        october=admin.get('/api/report?month=2026-10').text
        september=admin.get('/api/report?month=2026-09').text
        assert 'SGT boundary ticket' in october and '2026-10-01 00:00:00' in october
        assert 'SGT boundary ticket' not in september and 'Created SGT (UTC+8)' in october
        assert 'Location' not in october
        uid=post(admin,'/users',{'name':'Editable user','email':'edit@example.com','password':'TestPassword123!','role':'requester'}).json()['id']
        edit={'name':'Updated user','email':'updated@example.com','role':'infra','password':''}
        assert post(requester,f'/users/{uid}',edit).status_code==403
        assert post(admin,f'/users/{uid}',edit).status_code==200
        assert any(u['name']=='Updated user' and u['role']=='infra' for u in admin.get('/api/users').json())

def test_role_actions_and_assign_another_engineer():
    with TestClient(app) as admin, TestClient(app) as requester:
        login(admin,'admin@example.com');login(requester,'tm@example.com')
        config=admin.get('/api/settings').json()
        config['requester_actions']['note']={'label':'Requester reply','enabled':False}
        config['engineer_actions']['note']={'label':'Engineer reply','enabled':True}
        assert post(admin,'/settings',config).status_code==200
        tid=post(requester,'/tickets',{'title':'Assignment test','description':'Route to another engineer','category':'Others','domain':'UAT','severity':'Medium'}).json()['id']
        assert post(requester,f'/tickets/{tid}/actions',{'action':'note','text':'Disabled note'}).status_code==403
        assert post(admin,f'/tickets/{tid}/actions',{'action':'note','text':'Engineer note'}).status_code==200
        engineer=next(u for u in admin.get('/api/users').json() if u['email']=='infra@example.com')
        assigned=post(admin,f'/tickets/{tid}/actions',{'action':'assign','assignee_id':engineer['id']})
        assert assigned.status_code==200 and assigned.json()['assignee_id']==engineer['id']
        assert assigned.json()['status']=='In Progress'
        config['requester_actions']['note']['enabled']=True
        assert post(admin,'/settings',config).status_code==200
        assert post(requester,f'/tickets/{tid}/actions',{'action':'note','text':'Enabled reply'}).status_code==200
        config['requester_actions']['assign']={'label':'Unauthorized assign','enabled':True}
        assert post(admin,'/settings',config).status_code==422


def test_custom_actions_severity_delete_and_three_day_close():
    from datetime import timedelta
    with TestClient(app) as admin, TestClient(app) as requester:
        login(admin,'admin@example.com');login(requester,'tm@example.com')
        config=admin.get('/api/settings').json()
        config['requester_actions']['custom_followup']={'label':'Follow up','enabled':True}
        config['engineer_actions']['custom_vendor']={'label':'Vendor reply','enabled':True}
        assert post(admin,'/settings',config).status_code==200
        tid=post(requester,'/tickets',{'title':'Custom action test','description':'Three day timer and delete','category':'Others','domain':'UAT','severity':'Medium'}).json()['id']
        assert requester.get(f'/api/tickets/{tid}').json()['reference']==f'MOMCC-{tid:06d}'
        assert post(requester,f'/tickets/{tid}/actions',{'action':'custom_followup','text':'Please check'}).status_code==403
        assert post(requester,f'/tickets/{tid}/actions',{'action':'custom_vendor','text':'Wrong role'}).status_code==403
        assert post(admin,f'/tickets/{tid}/actions',{'action':'worklog','text':'Removed'}).status_code==403
        assert post(requester,f'/tickets/{tid}/severity',{'severity':'High'}).status_code==403
        assert post(admin,f'/tickets/{tid}/actions',{'action':'note','severity':'High'}).json()['severity']=='High'
        assert post(requester,f'/tickets/{tid}/actions',{'action':'note','text':'test','severity':'Low'}).status_code==403
        assert any(f'MOMCC-{tid:06d}' in n['text'] for n in requester.get('/api/notifications').json() if n['ticket_id']==tid)
        post(admin,f'/tickets/{tid}/actions',{'action':'assign'})
        post(admin,f'/tickets/{tid}/actions',{'action':'resolve','text':'Fixed'})
        with Session(engine) as session:
            t=session.get(Ticket,tid);t.resolved_at=now()-timedelta(days=2,hours=23);session.commit()
            auto_close(session);assert session.get(Ticket,tid).status=='Resolved, Pending Confirmation'
            t.resolved_at=now()-timedelta(days=3,minutes=1);session.commit()
            auto_close(session);assert session.get(Ticket,tid).status=='Closed'
        assert post(requester,f'/tickets/{tid}/delete',{}).status_code==403
        assert post(admin,f'/tickets/{tid}/delete',{}).status_code==200
        assert requester.get(f'/api/tickets/{tid}').status_code==404
        assert not any(n['ticket_id']==tid for n in requester.get('/api/notifications').json())
