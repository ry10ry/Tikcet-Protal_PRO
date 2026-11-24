from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from test_workflow import login, post
from app.changes import CRNotification
from app.main import app, engine
from app.services import SRNotification


def test_request_modules_can_be_paused_and_restored_independently(monkeypatch):
    with TestClient(app) as admin:
        login(admin, 'admin@example.com')
        cr = post(admin, '/changes', {'cr_date': '2041-01-01'}).raise_for_status().json()
        sr = post(admin, '/services', {'sr_date': '2041-01-01'}).raise_for_status().json()
        cr_path = f"/api/changes/{cr['id']}"
        sr_path = f"/api/services/{sr['id']}"
        workflow = admin.get('/api/cr-workflow').raise_for_status().json()
        user = admin.get('/api/me').raise_for_status().json()

        with Session(engine) as session:
            session.add(CRNotification(user_id=user['id'], cr_id=cr['id'], text='Test CR availability'))
            session.add(SRNotification(user_id=user['id'], sr_id=sr['id'], text='Test SR availability'))
            session.commit()

        monkeypatch.setenv('CHANGE_REQUEST_ENABLED', 'false')
        assert admin.get('/api/me').json()['request_modules'] == {'cr': False, 'sr': True}
        assert admin.get(cr_path).status_code == 404
        assert post(admin, '/changes', {'cr_date': '2041-01-01'}).status_code == 404
        assert admin.get('/api/changes/forms/schema').status_code == 404
        assert admin.get('/api/cr-workflow').status_code == 404
        assert post(admin, '/cr-workflow', workflow).status_code == 404
        assert admin.get('/api/internal/reports/cr?month=2041-01').status_code == 404
        assert admin.get(sr_path).status_code == 200
        assert admin.get('/api/internal/reports/sr?month=2041-01').status_code == 200

        notices = admin.get('/api/internal/notifications').raise_for_status().json()
        assert {n['kind'] for n in notices} == {'SR'}
        post(admin, '/internal/notifications/read', {}).raise_for_status()

        monkeypatch.setenv('SERVICE_REQUEST_ENABLED', 'false')
        assert admin.get('/api/me').json()['request_modules'] == {'cr': False, 'sr': False}
        assert admin.get(sr_path).status_code == 404
        assert admin.post(sr_path + '/actions', json={'version': sr['version'], 'action': 'submit'},
                          headers={'X-Requested-With': 'ServiceDesk'}).status_code == 404
        assert admin.get('/api/services/notifications').status_code == 404
        assert admin.get('/api/internal/notifications').json() == []
        assert admin.get('/api/report/fault-trend').status_code == 200
        assert admin.get('/api/report/engineer-intake').status_code == 200

        monkeypatch.setenv('CHANGE_REQUEST_ENABLED', 'true')
        assert admin.get('/api/me').json()['request_modules'] == {'cr': True, 'sr': False}
        assert admin.get(cr_path).json()['history'] == cr['history']
        assert admin.get('/api/cr-workflow').json() == workflow
        notices = admin.get('/api/internal/notifications').json()
        assert any(n['text'] == 'Test CR availability' and not n['read'] for n in notices)

        monkeypatch.setenv('SERVICE_REQUEST_ENABLED', 'true')
        assert admin.get(sr_path).json()['history'] == sr['history']
        notices = admin.get('/api/internal/notifications').json()
        assert any(n['text'] == 'Test SR availability' and n['read'] for n in notices)

        post(admin, cr_path.removeprefix('/api') + '/delete',
             {'version': cr['version'], 'action': 'comment'}).raise_for_status()
        post(admin, sr_path.removeprefix('/api') + '/delete',
             {'version': sr['version']}).raise_for_status()
