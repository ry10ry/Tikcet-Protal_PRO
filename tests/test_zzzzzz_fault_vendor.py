from fastapi.testclient import TestClient
from app.main import app
from test_services import H,login


def test_fault_vendor_wait_resume_resolution_and_permissions():
 with TestClient(app) as admin,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  config=admin.get('/api/settings').json()
  assert config['status_labels']['Pending 3rd Party']=='Pending 3rd Party'
  r=requester.post('/api/tickets',json=dict(title='Vendor assistance required',description='Issue requires vendor investigation',category=config['categories'][0],domain=config['domains'][0],severity=config['severities'][0]),headers=H).json()
  path='/api/tickets/'+str(r['id'])+'/actions'
  assert admin.post(path,json=dict(action='vendor',text='Vendor case ABC123'),headers=H).status_code==422
  assert admin.post(path,json=dict(action='assign',assignee_id=admin.get('/api/me').json()['id']),headers=H).status_code==200
  assert admin.post(path,json=dict(action='vendor',text=''),headers=H).status_code==422
  assert requester.post(path,json=dict(action='vendor',text='Vendor case ABC123'),headers=H).status_code==403
  response=admin.post(path,json=dict(action='vendor',text='Vendor case ABC123'),headers=H)
  assert response.status_code==200 and response.json()['status']=='Pending 3rd Party'
  assert admin.get('/api/tickets/'+str(r['id'])).json()['status']=='Pending 3rd Party'
  assert any('Pending 3rd Party' in e['text'] for e in admin.get('/api/tickets/'+str(r['id'])).json()['entries'])
  response=admin.post(path,json=dict(action='vendor_resume',text='Vendor supplied fix'),headers=H)
  assert response.status_code==200 and response.json()['status']=='In Progress'
  assert admin.post(path,json=dict(action='vendor_resume',text='Duplicate'),headers=H).status_code==422
  assert admin.post(path,json=dict(action='vendor',text='Awaiting further vendor work'),headers=H).status_code==200
  response=admin.post(path,json=dict(action='resolve',text='Vendor fixed the issue'),headers=H)
  assert response.status_code==200 and response.json()['status']=='Resolved, Pending Confirmation'
