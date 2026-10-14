"""PROD bootstrap creates only the chosen administrator on a fresh database."""
import os
import subprocess
import sys


def test_fresh_prod_bootstrap_and_health(tmp_path):
    env=os.environ.copy()
    env.update(DATABASE_URL='sqlite:///'+str(tmp_path/'fresh.db'),ADMIN_EMAIL='prod@example.com',ADMIN_PASSWORD='FreshProdTestPassword123!',COOKIE_SECURE='true',UPLOAD_DIR=str(tmp_path/'uploads'),LOG_DIR=str(tmp_path/'logs'))
    code='''
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from app.main import app,engine,User,Ticket
from app.changes import ChangeRequest
from app.services import ServiceRequest
with TestClient(app,base_url='https://prod.test') as c:
    assert c.get('/api/health').json()==dict(status='ok',environment='PROD',version='0.1')
    assert 'PROD v0.1' in c.get('/').text
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(User))==1
        assert s.scalar(select(User.email))=='prod@example.com'
        for model in (Ticket,ChangeRequest,ServiceRequest):
            assert s.scalar(select(func.count()).select_from(model))==0
    response=c.post('/api/login',json=dict(email='prod@example.com',password='FreshProdTestPassword123!'),headers={'X-Requested-With':'ServiceDesk'})
    assert response.status_code==200
    assert 'Secure' in response.headers['set-cookie']
    assert c.get('/api/services').json()['counts']['Total SR']==0
'''
    result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stderr
