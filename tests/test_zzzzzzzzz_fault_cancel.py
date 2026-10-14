from fastapi.testclient import TestClient
from app.main import app
from test_services import H,login


def test_requester_and_internal_staff_cancel_faults_preserving_history():
 with TestClient(app) as admin,TestClient(app) as requester,TestClient(app) as other,TestClient(app) as infra,TestClient(app) as tl,TestClient(app) as manager:
  for c,email in [(admin,'admin@example.com'),(requester,'tm@example.com'),(other,'other@example.com'),(infra,'sr-infra@example.com'),(tl,'sr-infra_tl@example.com'),(manager,'sr-infra_manager@example.com')]:login(c,email)
  config=admin.get('/api/settings').json()
  assert config['requester_actions']['cancel']['enabled'] and config['engineer_actions']['cancel']['enabled']
  def create():
   response=requester.post('/api/tickets',json=dict(title='Cancellation test',description='Request no longer needed',category=config['categories'][0],domain=config['domains'][0]),headers=H)
   assert response.status_code==200
   return '/api/tickets/'+str(response.json()['id'])
  p=create()
  assert other.post(p+'/actions',json=dict(action='cancel',text='Not my ticket'),headers=H).status_code==403
  assert requester.post(p+'/actions',json=dict(action='cancel',text=' '),headers=H).status_code==422
  assert requester.get(p).json()['status']=='New'
  for client in [requester,infra,tl,manager,admin]:
   p=create()
   assert admin.post(p+'/actions',json=dict(action='assign'),headers=H).status_code==200
   assert client.post(p+'/actions',json=dict(action='cancel',text='Request withdrawn'),headers=H).status_code==200
   r=admin.get(p).json()
   assert r['status']=='Cancelled' and any('Cancelled: Request withdrawn' in e['text'] for e in r['entries'])
   assert client.post(p+'/actions',json=dict(action='cancel',text='Again'),headers=H).status_code==409
  # Also available while awaiting vendor/customer or requester verification.
  for action in ['vendor','information','resolve']:
   p=create();admin.post(p+'/actions',json=dict(action='assign'),headers=H)
   assert admin.post(p+'/actions',json=dict(action=action,text='Workflow step'),headers=H).status_code==200
   assert requester.post(p+'/actions',json=dict(action='cancel',text='Withdrawn'),headers=H).status_code==200
  p=create();admin.post(p+'/actions',json=dict(action='assign'),headers=H)
  admin.post(p+'/actions',json=dict(action='resolve',text='Fixed'),headers=H)
  requester.post(p+'/actions',json=dict(action='close',text='Confirmed'),headers=H)
  assert requester.post(p+'/actions',json=dict(action='cancel',text='After close'),headers=H).status_code==409
  assert admin.post(p+'/actions',json=dict(action='cancel',text='After close'),headers=H).status_code==409
