from fastapi.testclient import TestClient
from app.main import app
from test_services import H,login,P


def test_admin_delete_user_preserves_records_and_revokes_sessions():
 with TestClient(app) as admin,TestClient(app) as target,TestClient(app) as requester:
  login(admin,'admin@example.com');login(requester,'tm@example.com')
  response=admin.post('/api/users',json=dict(name='Former Infra',email='delete-infra@example.com',password=P,role='infra'),headers=H)
  id=response.json()['id'];p='/api/users/'+str(id)
  login(target,'delete-infra@example.com')
  sr=target.post('/api/services',json={'sr_date':'2026-10-16'},headers=H).json()
  cr=target.post('/api/changes',json={'cr_date':'2026-10-16'},headers=H).json()
  assert target.post(p+'/delete',json={},headers=H).status_code==403
  assert requester.post(p+'/delete',json={},headers=H).status_code==403
  assert admin.post('/api/users/'+str(admin.get('/api/me').json()['id'])+'/delete',json={},headers=H).status_code==422
  assert admin.post(p+'/delete',json={},headers=H).status_code==200
  assert target.get('/api/me').status_code==401
  assert target.post('/api/login',json=dict(email='delete-infra@example.com',password=P),headers=H).status_code==401
  assert id not in [u['id'] for u in admin.get('/api/users').json()]
  assert admin.get('/api/services/'+str(sr['id'])).json()['owner']=='Former Infra'
  assert admin.get('/api/changes/'+str(cr['id'])).json()['owner']=='Former Infra'
  assert admin.post(p+'/delete',json={},headers=H).status_code==404
  assert admin.post(p,json=dict(name='Reactivated',email='delete-infra@example.com',role='infra',password=''),headers=H).status_code==404
