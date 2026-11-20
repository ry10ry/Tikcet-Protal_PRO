"""Staff-only Fault Ticket reporting, with Singapore calendar month boundaries."""

from collections import defaultdict
from datetime import timedelta

from fastapi import Depends
from sqlalchemy import Column, ForeignKey, Integer, case, func, or_, select
from sqlalchemy.orm import Session

from app.fault_content import FaultContent
from app.main import Base, Entry, Ticket, User, current_user, db, now, staff

SGT_OFFSET = timedelta(hours=8)
ASSIGNMENT_PREFIX = 'In Progress: Assigned to '
ENGINEER_ROLES = {'infra', 'infra_tl', 'infra_manager', 'admin'}


class FaultAssignment(Base):
    __tablename__ = 'fault_assignments'

    entry_id = Column(Integer, ForeignKey('entries.id', ondelete='CASCADE'), primary_key=True)
    # A null engineer marks a status comment that matches the legacy assignment text.
    engineer_id = Column(Integer, ForeignKey('users.id'))


def month_start(local_time, offset=0):
    year, month_index = divmod(local_time.year * 12 + local_time.month - 1 + offset, 12)
    return local_time.replace(year=year, month=month_index + 1, day=1,
                              hour=0, minute=0, second=0, microsecond=0)


def register_fault_reports(app):
    @app.get('/api/report/fault-trend')
    def fault_trend(user: User = Depends(current_user), session: Session = Depends(db)):
        staff(user)
        current = now()
        local_time = current + SGT_OFFSET
        months = [month_start(local_time, offset) for offset in range(-11, 1)]
        utc_starts = [month - SGT_OFFSET for month in months]
        bucket = case(
            *((Ticket.created_at < start, i) for i, start in enumerate(utc_starts[1:])),
            else_=len(months) - 1,
        ).label('month_bucket')
        counts = {
            index: (total, internal or 0)
            for index, total, internal in session.execute(
                select(bucket, func.count(Ticket.id),
                       func.sum(case((FaultContent.visibility == 'Internal', 1), else_=0)))
                .outerjoin(FaultContent, FaultContent.ticket_id == Ticket.id)
                .where(Ticket.created_at >= utc_starts[0], Ticket.created_at <= current)
                .group_by('month_bucket')
            )
        }
        result = []
        for i, month in enumerate(months):
            total, internal = counts.get(i, (0, 0))
            result.append({'month': month.strftime('%Y-%m'), 'total': total,
                           'public': total - internal, 'internal': internal})
        return {'months': result, 'as_of': local_time.date().isoformat()}

    @app.get('/api/report/engineer-intake')
    def engineer_intake(user: User = Depends(current_user), session: Session = Depends(db)):
        staff(user)
        current = now()
        local_time = current + SGT_OFFSET
        start = month_start(local_time) - SGT_OFFSET
        people = session.execute(select(User.id, User.name, User.role).order_by(User.name, User.id)).all()
        ids_by_name = defaultdict(list)
        for person in people:
            ids_by_name[person.name].append(person.id)

        all_tickets = defaultdict(set)
        monthly_tickets = defaultdict(set)
        unmatched = 0
        stmt = (
            select(Entry.ticket_id, Entry.created_at, Entry.text,
                   FaultAssignment.entry_id, FaultAssignment.engineer_id)
            .outerjoin(FaultAssignment, FaultAssignment.entry_id == Entry.id)
            .where(Entry.kind == 'Status', Entry.created_at <= current,
                   or_(FaultAssignment.entry_id.is_not(None), Entry.text.startswith(ASSIGNMENT_PREFIX)))
        )
        for ticket_id, assigned_at, description, assignment_id, engineer_id in session.execute(stmt):
            if assignment_id is None:
                if not description.startswith(ASSIGNMENT_PREFIX):
                    continue
                matches = ids_by_name[description[len(ASSIGNMENT_PREFIX):]]
                if len(matches) != 1:
                    unmatched += 1
                    continue
                engineer_id = matches[0]
            if engineer_id is not None:
                all_tickets[engineer_id].add(ticket_id)
                if assigned_at >= start:
                    monthly_tickets[engineer_id].add(ticket_id)

        rows = [
            {'name': person.name, 'month': len(monthly_tickets[person.id]),
             'total': len(all_tickets[person.id])}
            for person in people
            if person.role in ENGINEER_ROLES or person.id in all_tickets
        ]
        return {
            'month': local_time.strftime('%Y-%m'),
            'rows': rows,
            'totals': {key: sum(row[key] for row in rows) for key in ('month', 'total')},
            'unmatched_legacy_entries': unmatched,
        }
