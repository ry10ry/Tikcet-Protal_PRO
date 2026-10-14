import logging
import re
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.logging_support import configure_logging,RequestLoggingMiddleware


def test_error_log_request_reference_safe_traceback_and_503(tmp_path,monkeypatch):
 monkeypatch.setenv('LOG_DIR',str(tmp_path));monkeypatch.setenv('WAHA_API_KEY','configured-key-secret')
 configure_logging()
 app=FastAPI();app.add_middleware(RequestLoggingMiddleware)
 @app.post('/fail')
 async def fail(request:Request):
  payload=await request.json()
  raise RuntimeError(payload)
 @app.get('/database')
 def database():raise OperationalError('sensitive SQL',{'password':'sql-secret'},OSError(111,'Connection refused'))
 @app.get('/expected')
 def expected():raise HTTPException(422,'Required field missing')
 with TestClient(app) as c:
  result=c.post('/fail?api_key=query-secret',json={'password':'body-secret','attachment':'BASE64_PRIVATE_CONTENT'},headers={'Cookie':'session=cookie-secret','Authorization':'Bearer header-secret','X-Request-ID':'untrusted-client-id'})
  assert result.status_code==500
  id=result.headers['x-request-id'];assert re.fullmatch('[a-f0-9]{32}',id)
  assert result.json()['request_id']==id and id in result.json()['detail']
  second=c.get('/database');assert second.status_code==503 and second.headers['x-request-id']!=id
  expected=c.get('/expected');assert expected.status_code==422 and expected.json()['detail']=='Required field missing'
 text=(tmp_path/'web.log').read_text()
 assert id in text and 'Traceback' in text and 'RuntimeError' in text and 'OperationalError' in text
 assert 'route=/fail' in text and 'status=503' in text and 'error_code=111' in text
 for secret in ['body-secret','BASE64_PRIVATE_CONTENT','query-secret','cookie-secret','header-secret','configured-key-secret','sql-secret','sensitive SQL']:
  assert secret not in text
 assert 'untrusted-client-id' not in text


def test_log_redaction_service_files_and_rotation(tmp_path,monkeypatch):
 from logging.handlers import RotatingFileHandler
 monkeypatch.setenv('LOG_DIR',str(tmp_path));monkeypatch.setenv('LOG_SERVICE','scheduler')
 monkeypatch.setenv('WAHA_API_KEY','sample-private-api-key')
 configure_logging()
 logger=logging.getLogger('servicedesk.scheduler')
 logger.warning('Known secret filtered: %s', 'sample-private-api-key')
 logger.info('Normal task INFO should not be recorded')
 text=(tmp_path/'scheduler.log').read_text()
 assert 'Normal task INFO' not in text
 assert 'sample-private-api-key' not in text and '[REDACTED]' in text and 'service=scheduler' in text
 handler=next(h for h in logging.getLogger().handlers if isinstance(h,RotatingFileHandler))
 assert handler.maxBytes==5*1024*1024 and handler.backupCount==5
 handler.maxBytes=512
 for i in range(40):logger.warning('Rotation check %s %s',i,'x'*100)
 assert 1<len(list(tmp_path.glob('scheduler.log*')))<=6


def test_database_startup_failure_is_logged_without_suppressing_failure(tmp_path,monkeypatch):
 import pytest
 from app.main import app,Base
 monkeypatch.setenv('LOG_DIR',str(tmp_path));monkeypatch.setenv('LOG_SERVICE','web')
 configure_logging()
 def unavailable(*args,**kwargs):raise OperationalError('private statement',{},OSError(111,'Connection refused'))
 monkeypatch.setattr(Base.metadata,'create_all',unavailable)
 with pytest.raises(OperationalError):
  with TestClient(app):pass
 text=(tmp_path/'web.log').read_text()
 assert 'Application database initialization failed' in text and 'error_code=111' in text
 assert 'private statement' not in text
