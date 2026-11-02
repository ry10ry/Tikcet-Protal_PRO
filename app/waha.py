"""Durable Fault creation and assignment WhatsApp group delivery through WAHA."""
import json
import logging
import os
import uuid
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from sqlalchemy import Column,Integer,String,Text,DateTime,ForeignKey,select,update
from sqlalchemy.orm import Session
from app.main import Base,now

logger=logging.getLogger(__name__)

class OutboxFields:

    id=Column(Integer,primary_key=True)
    ticket_id=Column(Integer,ForeignKey('tickets.id'),nullable=False)
    chat_id=Column(String(255),nullable=False,default='')
    session_name=Column(String(100),nullable=False,default='default')
    text=Column(Text,nullable=False)
    status=Column(String(20),nullable=False,default='pending')
    attempts=Column(Integer,nullable=False,default=0)
    created_at=Column(DateTime,nullable=False,default=now)
    next_attempt_at=Column(DateTime,nullable=False,default=now,index=True)
    sent_at=Column(DateTime)
    lease_token=Column(String(32))
    last_error=Column(String(200))

class WhatsAppOutbox(OutboxFields,Base):
    __tablename__='whatsapp_outbox'
    ticket_id=Column(Integer,ForeignKey('tickets.id'),nullable=False,unique=True)

class WhatsAppAssignmentOutbox(OutboxFields,Base):
    __tablename__='whatsapp_assignment_outbox'

def enabled():return os.environ.get('WAHA_ENABLED','false').lower()=='true'

def enqueue_new_fault(session,ticket,user):
    if not enabled():return
    from app.cr_email import singapore_time
    one_line=lambda value:' '.join(str(value).split())
    lines=['New Fault Ticket',f'Number: MOMCC-{ticket.id:06d}',
        'Subject: '+one_line(ticket.title),'Category: '+one_line(ticket.category),'Domain: '+one_line(ticket.domain),
        'Raised by: '+one_line(user.name),'Reported: '+singapore_time(ticket.created_at)]
    session.add(WhatsAppOutbox(ticket_id=ticket.id,
        chat_id=os.environ.get('WAHA_GROUP_CHAT_ID','').strip(),
        session_name=os.environ.get('WAHA_SESSION','default').strip() or 'default',
        text='\n'.join(lines)))

def enqueue_assignment(session,ticket,assignee):
    if not enabled():return
    one_line=lambda value:' '.join(str(value).split())
    session.add(WhatsAppAssignmentOutbox(ticket_id=ticket.id,
        chat_id=os.environ.get('WAHA_GROUP_CHAT_ID','').strip(),
        session_name=os.environ.get('WAHA_SESSION','default').strip() or 'default',
        text='\n'.join(['Fault Ticket Assigned',f'Number: MOMCC-{ticket.id:06d}',
            'Subject: '+one_line(ticket.title),'Engineer: '+one_line(assignee.name)])))

def send_text(base_url,api_key,session_name,chat_id,text):
    payload=json.dumps({'session':session_name,'chatId':chat_id,'text':text,'linkPreview':False}).encode('utf-8')
    request=Request(base_url.rstrip('/')+'/api/sendText',data=payload,
        headers={'Content-Type':'application/json','X-Api-Key':api_key},method='POST')
    with urlopen(request,timeout=10) as response:
        result=json.loads(response.read(1024*1024))
        if not isinstance(result,dict) or not result.get('id') or result.get('error'):
            raise ValueError('WAHA did not acknowledge the message')

def process_outbox(engine,limit=10):
    processed=_process_outbox(engine,WhatsAppOutbox,limit)
    return processed+_process_outbox(engine,WhatsAppAssignmentOutbox,max(0,limit-processed))

def _process_outbox(engine,model,limit):
    if not enabled():return 0
    base_url=os.environ.get('WAHA_URL','').strip()
    api_key=os.environ.get('WAHA_API_KEY','').strip()
    fallback_group=os.environ.get('WAHA_GROUP_CHAT_ID','').strip()
    parsed=urlparse(base_url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or not api_key or not fallback_group.endswith('@g.us'):
        logger.warning('WhatsApp delivery is enabled but WAHA configuration is incomplete; queued messages retained')
        return 0
    processed=0
    for _ in range(limit):
        with Session(engine) as session:
            due=now()
            condition=(model.status.in_(('pending','sending')) & (model.next_attempt_at<=due))
            row=session.scalar(select(model).where(condition).order_by(model.id).limit(1).with_for_update(skip_locked=True))
            if not row:break
            token=uuid.uuid4().hex
            claimed=session.execute(update(model).where(model.id==row.id,condition).values(status='sending',lease_token=token,attempts=model.attempts+1,next_attempt_at=due+timedelta(minutes=3)))
            if claimed.rowcount!=1:session.rollback();continue
            session.refresh(row)
            id,attempts,chat_id,session_name,text=row.id,row.attempts,row.chat_id or fallback_group,row.session_name,'\n'.join(row.text.splitlines()[:7]).replace('*New Fault Ticket*','New Fault Ticket',1)
            session.commit()
        error=None
        try:
            if not chat_id.endswith('@g.us'):raise ValueError('Destination must be a WhatsApp group')
            send_text(base_url,api_key,session_name,chat_id,text)
        except HTTPError as exc:error='WAHA HTTP '+str(exc.code)
        except (URLError,TimeoutError,OSError):error='WAHA connection failed or timed out'
        except (ValueError,TypeError):error='WAHA response or group configuration invalid'
        except Exception:error='WAHA delivery failed'
        with Session(engine) as session:
            values=dict(status='sent',sent_at=now(),last_error=None,lease_token=None) if error is None else dict(status='pending',next_attempt_at=now()+timedelta(seconds=min(900,30*(2**min(attempts-1,5)))),last_error=error,lease_token=None)
            session.execute(update(model).where(model.id==id,model.lease_token==token).values(**values))
            session.commit()
        processed+=1
        if error:logger.warning('WhatsApp queue item %s: %s; retry scheduled',id,error)
        else:logger.info('WhatsApp queue item %s sent',id)
    return processed
