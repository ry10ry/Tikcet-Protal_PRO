"""Rotating service logs, safe tracebacks and HTTP request correlation."""
import copy
import logging
import os
import re
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy.exc import OperationalError, TimeoutError as DatabaseTimeout
from starlette.responses import JSONResponse

request_id=ContextVar('request_id',default='-')

class SafeFormatter(logging.Formatter):
    def formatTime(self,record,datefmt=None):
        return datetime.fromtimestamp(record.created,ZoneInfo('Asia/Singapore')).isoformat(timespec='milliseconds')

    def formatException(self,info):
        # Stack frames and exception classes are useful without exposing exception
        # values, SQL parameters, request bodies, passwords or attachment bytes.
        parts=[];exc=info[1];seen=set()
        while exc is not None and id(exc) not in seen:
            seen.add(id(exc))
            parts.append('Traceback (exception values omitted):\n')
            parts.extend(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n' for frame in traceback.extract_tb(exc.__traceback__))
            name=type(exc).__module__+'.'+type(exc).__name__
            code=getattr(exc,'errno',None)
            original=getattr(exc,'orig',None)
            if original and original.args and isinstance(original.args[0],int):code=original.args[0]
            parts.append(name+(f' [error_code={code}]' if isinstance(code,int) else '')+'\n')
            exc=exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
        return ''.join(parts).rstrip()

    def format(self,record):
        record=copy.copy(record);record.exc_text=None
        record.request_id=request_id.get()
        text=super().format(record)
        for key,value in os.environ.items():
            if len(value)>=6 and any(s in key.upper() for s in ('PASSWORD','SECRET','TOKEN','API_KEY','DATABASE_URL')):
                text=text.replace(value,'[REDACTED]')
        text=re.sub(r'(://[^\s:/]+:)[^\s@]+@',r'\1[REDACTED]@',text)
        return text

def configure_logging():
    service='scheduler' if os.environ.get('LOG_SERVICE')=='scheduler' else 'web'
    root=logging.getLogger();root.setLevel(logging.WARNING)
    for handler in list(root.handlers):
        if getattr(handler,'servicedesk_handler',False):root.removeHandler(handler);handler.close()
    formatter=SafeFormatter('%(asctime)s %(levelname)s service='+service+' request_id=%(request_id)s %(name)s: %(message)s')
    console=logging.StreamHandler(sys.stderr);console.servicedesk_handler=True;console.setLevel(logging.WARNING);console.setFormatter(formatter);root.addHandler(console)
    try:
        directory=Path(os.environ.get('LOG_DIR','/tmp/momcc-logs'));directory.mkdir(parents=True,exist_ok=True)
        handler=RotatingFileHandler(directory/(service+'.log'),maxBytes=5*1024*1024,backupCount=5,encoding='utf-8',delay=False)
        handler.servicedesk_handler=True;handler.setLevel(logging.WARNING);handler.setFormatter(formatter);root.addHandler(handler)
    except OSError:
        root.warning('File logging unavailable; check LOG_DIR permissions. Console logging remains available.')
    # Route Uvicorn lifecycle/errors through the same safe formatter. HTTP access
    # logging below uses route templates rather than URLs containing query data.
    for name in ('uvicorn','uvicorn.error'):
        logger=logging.getLogger(name);logger.handlers.clear();logger.propagate=True
    logging.getLogger('uvicorn.access').disabled=True
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

class RequestLoggingMiddleware:
    def __init__(self,app):self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        id=uuid.uuid4().hex
        token=request_id.set(id);scope.setdefault('state',{})['request_id']=id
        started=False;status=500;begin=time.monotonic()
        logger=logging.getLogger('servicedesk.http')
        async def wrapped_send(message):
            nonlocal started,status
            if message['type']=='http.response.start':
                started=True;status=message['status']
                message={**message,'headers':[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'x-request-id']+[(b'x-request-id',id.encode())]}
            await send(message)
        try:
            await self.app(scope,receive,wrapped_send)
        except Exception as exc:
            unavailable=isinstance(exc,(OperationalError,DatabaseTimeout))
            status=503 if unavailable else 500
            logger.exception('Database unavailable' if unavailable else 'Unhandled request exception')
            if started:raise
            detail=('Service temporarily unavailable. Please try again.' if unavailable else 'Unexpected server error. Please try again.')+' Reference: '+id
            await JSONResponse({'detail':detail,'request_id':id},status_code=status)(scope,receive,wrapped_send)
        finally:
            route=getattr(scope.get('route'),'path','<unmatched>')
            logger.log(logging.WARNING if status>=400 else logging.INFO,
                'HTTP method=%s route=%s status=%s duration_ms=%.1f',scope.get('method','?'),route,status,(time.monotonic()-begin)*1000)
            request_id.reset(token)
