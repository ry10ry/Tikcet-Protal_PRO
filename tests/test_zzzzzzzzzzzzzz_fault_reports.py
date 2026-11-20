from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from test_workflow import login, post
from app import fault_reports
from app.main import Entry, Ticket, app, engine


def test_fault_trend_and_intake(monkeypatch):
    monkeypatch.setattr(fault_reports, 'now', lambda: datetime(2040, 11, 20))
    with TestClient(app) as admin, TestClient(app) as requester:
        login(admin, 'admin@example.com')
        ids = {}
        for name, role in [('Report A', 'infra'), ('Report B', 'infra'),
                           ('Report Zero', 'infra'), ('Report Requester', 'requester')]:
            email = name.replace(' ', '-').lower() + '@example.com'
            response = post(admin, '/users', {
                'name': name, 'role': role, 'email': email, 'password': 'TestPassword123!',
            })
            assert response.status_code == 200
            ids[name] = response.json()['id']
        login(requester, 'report-requester@example.com')
        for endpoint in ('fault-trend', 'engineer-intake'):
            assert requester.get('/api/report/' + endpoint).status_code == 403

        ticket_ids = {}
        for visibility in ('Public', 'Internal'):
            response = post(admin, '/tickets', {
                'title': f'Report {visibility}', 'description': 'Report test ticket',
                'category': 'Others', 'domain': 'UAT', 'location': 'MOMCC',
                'severity': 'High', 'visibility': visibility,
            })
            assert response.status_code == 200
            ticket_ids[visibility] = response.json()['id']

        public_id = ticket_ids['Public']
        internal_id = ticket_ids['Internal']
        path = f'/tickets/{public_id}/actions'
        for name in ('Report A', 'Report B', 'Report A'):
            assert post(admin, path, {'action': 'assign', 'assignee_id': ids[name]}).status_code == 200
        assert post(admin, path, {'action': 'vendor', 'text': 'Waiting'}).status_code == 200
        assert post(admin, path, {'action': 'vendor_resume', 'text': 'Assigned to Report Zero'}).status_code == 200

        boundary = datetime(2040, 10, 31, 16)
        before = datetime(2040, 10, 31, 15, 59, 59)
        with Session(engine) as session:
            session.get(Ticket, public_id).created_at = before
            session.get(Ticket, internal_id).created_at = boundary
            entries = session.scalars(
                select(Entry).where(Entry.ticket_id == public_id,
                                    Entry.text.startswith(fault_reports.ASSIGNMENT_PREFIX)).order_by(Entry.id)
            ).all()
            for entry, timestamp in zip(entries, (before, boundary, boundary, boundary), strict=True):
                entry.created_at = timestamp
            session.add(Entry(ticket_id=internal_id, kind='Status', created_at=before,
                              text=fault_reports.ASSIGNMENT_PREFIX + 'Report B'))
            session.add(Entry(ticket_id=internal_id, kind='Status', created_at=boundary,
                              text=fault_reports.ASSIGNMENT_PREFIX + 'Unknown Former Engineer'))
            session.commit()

        trend = admin.get('/api/report/fault-trend').json()['months']
        assert len(trend) == 12
        assert trend[-3:] == [
            {'month': '2040-09', 'total': 0, 'public': 0, 'internal': 0},
            {'month': '2040-10', 'total': 1, 'public': 1, 'internal': 0},
            {'month': '2040-11', 'total': 1, 'public': 0, 'internal': 1},
        ]
        intake = admin.get('/api/report/engineer-intake').json()
        rows = {row['name']: (row['month'], row['total']) for row in intake['rows']}
        assert {name: rows[name] for name in ('Report A', 'Report B', 'Report Zero')} == {
            'Report A': (1, 1), 'Report B': (1, 2), 'Report Zero': (0, 0),
        }
        assert intake['totals']['month'] == 2
        assert intake['unmatched_legacy_entries'] >= 1
