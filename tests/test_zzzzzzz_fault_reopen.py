from fastapi.testclient import TestClient
from app.main import app
from test_services import H,login


def test_requester_comment_reopens_pending_confirmation_without_severity_input():
 with TestClient(app) as admin,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  config=admin.get('/api/settings').json()
  response=requester.post('/api/tickets',json=dict(title='Issue persists',description='Fault needs further attention',category=config['categories'][0],domain=config['domains'][0]),headers=H)
  assert response.status_code==200
  id=response.json()['id'];p='/api/tickets/'+str(id)
  assert admin.post(p+'/actions',json=dict(action='assign'),headers=H).status_code==200
  assert admin.post(p+'/actions',json=dict(action='resolve',text='Initial fix'),headers=H).status_code==200
  assert requester.post(p+'/actions',json=dict(action='note',text=''),headers=H).status_code==422
  assert requester.get(p).json()['status']=='Resolved, Pending Confirmation'
  assert admin.post(p+'/actions',json=dict(action='note',text='Infra follow-up'),headers=H).status_code==200
  assert requester.get(p).json()['status']=='Resolved, Pending Confirmation'
  assert requester.post(p+'/actions',json=dict(action='note',text='Still facing the same issue'),headers=H).status_code==200
  r=requester.get(p).json()
  assert r['status']=='In Progress' and r['resolved_at'] is None and not r['resolution']
  assert any('issue persists' in e['text'] for e in r['entries'])
  assert any('Still facing the same issue' in e['text'] for e in r['entries'])
  assert requester.post(p+'/actions',json=dict(action='close',text='Close'),headers=H).status_code==422
  assert admin.post(p+'/actions',json=dict(action='resolve',text='Second fix'),headers=H).status_code==200
  assert requester.post(p+'/actions',json=dict(action='close',text='Confirmed resolved'),headers=H).status_code==200
  assert requester.post(p+'/actions',json=dict(action='note',text='Comment after closure'),headers=H).status_code==409
