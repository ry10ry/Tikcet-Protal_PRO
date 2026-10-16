"""One-year, portable offline archives with separately verified attachment cleanup."""
import csv
import hashlib
import io
import json
import logging
import os
import re
import shutil
import time
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote
from fastapi import Depends,HTTPException
from sqlalchemy import Column,Integer,String,Text,DateTime,UniqueConstraint,select,update,func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import LONGTEXT
from app.main import Base,Setting,User,Ticket,Entry,Attachment,now,current_user,db,write_guard

logger=logging.getLogger(__name__)
MARKER='.momcc-archive-target'

class ArchiveRecord(Base):
    __tablename__='archive_records'
    id=Column(Integer,primary_key=True)
    kind=Column(String(10),nullable=False)
    record_id=Column(Integer,nullable=False)
    number=Column(String(80),nullable=False)
    folder=Column(String(180),nullable=False)
    target=Column(String(100),nullable=False)
    state=Column(String(20),nullable=False,default='copied')
    summary=Column(Text().with_variant(LONGTEXT(),'mysql'),nullable=False)
    created_at=Column(DateTime,nullable=False,default=now)
    copied_by=Column(Integer)
    purged_by=Column(Integer)
    purged_at=Column(DateTime)
    __table_args__=(UniqueConstraint('kind','record_id'),)

class ArchiveFile(Base):
    __tablename__='archive_files'
    id=Column(Integer,primary_key=True)
    archive_id=Column(Integer,nullable=False,index=True)
    kind=Column(String(10),nullable=False)
    file_id=Column(Integer,nullable=False)
    path=Column(String(500),nullable=False)
    size=Column(Integer,nullable=False)
    sha256=Column(String(64),nullable=False)
    __table_args__=(UniqueConstraint('kind','file_id'),)

class ArchiveExport(Base):
    __tablename__='archive_exports'
    archive_id=Column(Integer,primary_key=True)
    location=Column(String(1000),nullable=False)
    exported_at=Column(DateTime,nullable=False,default=now)

def cutoff():
    value=now()+timedelta(hours=8)
    try:value=value.replace(year=value.year-1)
    except ValueError:value=value.replace(year=value.year-1,day=28)
    return value-timedelta(hours=8)

def info(s,kind,id):
    key='archive_records_'+kind
    if key not in s.info:s.info[key]={r.record_id:r for r in s.execute(select(ArchiveRecord.record_id,ArchiveRecord.state,ArchiveRecord.folder,ArchiveExport.location).outerjoin(ArchiveExport,ArchiveExport.archive_id==ArchiveRecord.id).where(ArchiveRecord.kind==kind))}
    return s.info[key].get(id)

def fields(s,kind,id):
    row=info(s,kind,id)
    return [('offline' if row.location else row.state),(row.location+' / '+row.folder+'/index.html' if row.location else row.folder+'/index.html')] if row else ['','']

def writable(s,kind,id):
    if s.scalar(select(ArchiveRecord).where(ArchiveRecord.kind==kind,ArchiveRecord.record_id==id).with_for_update()):raise HTTPException(409,'Archived records are read-only; the historical record is retained for reports')

def root():
    value=os.environ.get('ARCHIVE_ROOT','')
    if not value:raise HTTPException(503,'Archive storage is not configured')
    path=Path(value)
    try:
        target=(path/MARKER).read_text().strip()
        uuid.UUID(target)
    except (OSError,ValueError):raise HTTPException(503,'Archive disk is unavailable or its target marker is missing')
    return path,target

def upload_dir():
    from app.main import UPLOAD_DIR
    return UPLOAD_DIR

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def saved_path(s,kind,file_id):
    file=s.scalar(select(ArchiveFile).where(ArchiveFile.kind==kind,ArchiveFile.file_id==file_id))
    if not file:return None
    archive=s.execute(select(ArchiveRecord.target,ArchiveRecord.folder).where(ArchiveRecord.id==file.archive_id)).one()
    exported=s.get(ArchiveExport,file.archive_id)
    if exported:
        raise HTTPException(503,'Attachment archived offline. Connect the archive disk and open its index.html. Location: '+exported.location+' / '+archive.folder)
    base,target=root()
    if archive.target!=target:raise HTTPException(503,'Connect the correct archive disk')
    path=base/archive.folder/file.path
    if not path.resolve().is_relative_to(base.resolve()):raise HTTPException(503,'Invalid archive path')
    if not path.is_file() or path.stat().st_size!=file.size or digest(path)!=file.sha256:
        raise HTTPException(503,'Archived attachment unavailable or failed integrity verification')
    return path

def file_bytes(s,kind,file_id,data):
    if data:return data
    path=saved_path(s,kind,file_id)
    return path.read_bytes() if path else data

def file_size(s,kind,file_id,data):
    if data:return len(data)
    key='archive_sizes_'+kind
    if key not in s.info:s.info[key]=dict(s.execute(select(ArchiveFile.file_id,ArchiveFile.size).where(ArchiveFile.kind==kind)).all())
    return s.info[key].get(file_id,0)

def models():
    from app.changes import ChangeRequest,CRHistory,CRFile
    from app.services import ServiceRequest,SRHistory,SRFile
    return {'FAULT':(Ticket,Entry,Attachment),'CR':(ChangeRequest,CRHistory,CRFile),'SR':(ServiceRequest,SRHistory,SRFile)}

def completed(s,kind,row):
    if kind=='FAULT':
        if row.status=='Closed':return row.closed_at
        if row.status=='Cancelled':
            entry=s.scalar(select(Entry).where(Entry.ticket_id==row.id,Entry.kind=='Status',Entry.text.like('Cancelled%')).order_by(Entry.id.desc()))
            return entry.created_at if entry else row.updated_at
    else:
        _,history,_=models()[kind]
        key=history.cr_id if kind=='CR' else history.sr_id
        action='close' if kind=='CR' else 'approve'
        if row.status==('Closed' if kind=='CR' else 'Approved'):
            entry=s.scalar(select(history).where(key==row.id,history.action==action).order_by(history.id.desc()))
            return entry.created_at if entry else None
    return None

def candidates(s):
    for kind,(model,_,_) in models().items():
        statuses=['Closed','Cancelled'] if kind=='FAULT' else ['Closed'] if kind=='CR' else ['Approved']
        for row in s.scalars(select(model).where(model.status.in_(statuses)).order_by(model.id)):
            if info(s,kind,row.id):continue
            date=completed(s,kind,row)
            if date and date<=cutoff():yield kind,row,date

def person(s,id):
    u=s.get(User,id) if id else None
    return u.name if u else 'System'

def capture(s,kind,row,date):
    _,history,file_model=models()[kind]
    key=history.ticket_id if kind=='FAULT' else history.cr_id if kind=='CR' else history.sr_id
    file_key=file_model.ticket_id if kind=='FAULT' else file_model.cr_id if kind=='CR' else file_model.sr_id
    number=f'MOMCC-{row.id:06d}' if kind=='FAULT' else row.number
    owner_id=row.requester_id if kind=='FAULT' else row.owner_id
    content={c.name:getattr(row,c.name) for c in row.__table__.columns}
    if kind=='CR':content['content']=json.loads(row.content)
    if kind=='FAULT':
        from app.fault_content import metadata
        content.update(metadata(s,row.id))
    records=[]
    for h in s.scalars(select(history).where(key==row.id).order_by(history.id)):
        item={c.name:getattr(h,c.name) for c in h.__table__.columns}
        item['actor']=person(s,h.user_id if kind=='FAULT' else h.actor_id)
        if kind!='FAULT':item['snapshot']=json.loads(h.snapshot)
        records.append(item)
    summary={'kind':kind,'number':number,'status':row.status,'subject':row.title if kind=='FAULT' else json.loads(row.content).get('description','') if kind=='CR' else row.subject,
             'owner':person(s,owner_id),'created':(row.created_at+timedelta(hours=8)).isoformat(sep=' ',timespec='seconds')+' SGT','completed':(date+timedelta(hours=8)).isoformat(sep=' ',timespec='seconds')+' SGT'}
    data={'format_version':1,'summary':summary,'record':content,'history':records,'attachments':[]}
    return data,file_model,file_key

def write_file(path,data):
    with path.open('wb') as f:f.write(data);f.flush();os.fsync(f.fileno())

def page(data,index=False):
    encoded=json.dumps(data,ensure_ascii=False,default=str).replace('<','\\u003c')
    return ('''<!doctype html><meta charset="utf-8"><title>MOMCC Archive</title><style>body{font:15px Arial;margin:30px;color:#24324b}input,select,button{padding:10px;margin:5px}article{padding:16px;border:1px solid #ddd;margin:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%;max-height:500px}a{color:#2357d8}table{border-collapse:collapse}td,th{border:1px solid #64748b;padding:8px}</style><h1>MOMCC Archive</h1><div id="controls"></div><main></main><script type="application/json" id="data">'''+encoded+'''</script><script>
const data=JSON.parse(document.querySelector('#data').textContent),main=document.querySelector('main'),controls=document.querySelector('#controls');
const node=(tag,text,parent)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;(parent||main).append(n);return n};
const csvCell=v=>{let text=String(v??'');if(/^[=+@-]/.test(text.trimStart()))text=String.fromCharCode(39)+text;return '"'+text.replaceAll('"','""')+'"'};
if(Array.isArray(data)){
 controls.innerHTML='<input id="search" placeholder="Search number, subject or owner"><select id="kind"><option value="">All types</option><option>FAULT</option><option>CR</option><option>SR</option></select><input id="from" type="date" aria-label="Completed from"><input id="to" type="date" aria-label="Completed to"><button id="csv">Export CSV</button>';
 let shown=[];function draw(){main.replaceChildren();const q=document.querySelector('#search').value.toLowerCase(),k=document.querySelector('#kind').value,from=document.querySelector('#from').value,to=document.querySelector('#to').value;shown=data.filter(r=>(!k||r.kind===k)&&(!from||r.completed.slice(0,10)>=from)&&(!to||r.completed.slice(0,10)<=to)&&[r.number,r.subject,r.owner].join(' ').toLowerCase().includes(q));node('p',shown.length+' records');for(const r of shown){const a=node('article');const link=node('a',r.number+' — '+r.subject,a);link.href=r.path;node('p',r.kind+' | '+r.status+' | '+r.owner+' | Completed: '+r.completed,a)}}
 controls.oninput=draw;document.querySelector('#csv').onclick=()=>{const columns=['kind','number','subject','owner','status','created','completed','description','scope','approval_records','attachments','attachment_paths','path'];const text=String.fromCharCode(65279)+[columns.map(csvCell).join(','),...shown.map(r=>columns.map(k=>csvCell(r[k])).join(','))].join(String.fromCharCode(13,10));const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='MOMCC-Archive.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};draw();
}else{
 node('h2',data.summary.number+' — '+data.summary.subject);node('p',data.summary.status+' | '+data.summary.owner+' | Completed: '+data.summary.completed);
 node('h2','Record');const content=data.record.content||data.record;for(const [key,value] of Object.entries(content)){if(key==='severity'||key.startsWith('_')||value===null||value==='')continue;const a=node('article');node('strong',key.replaceAll('_',' '),a);if(key==='description_html'){const view=node('div',undefined,a);view.innerHTML=value}else node('pre',typeof value==='object'?JSON.stringify(value,null,2):String(value),a)}node('h2','Comments, approvals and history');for(const h of data.history){const a=node('article');node('strong',(h.actor||'')+' — '+(h.action||h.kind||''),a);node('p',String(h.created_at||'')+' UTC',a);node('pre',h.comment||h.reason||h.text||'',a);const details=node('details',undefined,a);node('summary','Full history and approval snapshot',details);node('pre',JSON.stringify(h,null,2),details)}
 node('h2','Attachments');for(const f of data.attachments){const a=node('article');const link=node('a',f.filename+' — file '+f.id+(f.version?' / revision '+f.version:'')+(f.active===false?' / historical removed file':'')+' ('+f.size+' bytes)',a);link.href=f.path;if(f.preview){const img=node('img',undefined,a);img.loading='lazy';img.src=f.path;img.alt=f.filename}}node('p','Complete machine-readable record:');node('a','record.json').href='record.json';
}</script>''').encode('utf-8')

def verify(folder):
    manifest=json.loads((folder/'manifest.json').read_text())
    for file in manifest:
        path=folder/file['path']
        if not path.resolve().is_relative_to(folder.resolve()) or not path.is_file() or path.stat().st_size!=file['size'] or digest(path)!=file['sha256']:
            raise HTTPException(409,'Archive integrity verification failed; online files were not cleared')

def build_index(base):
    rows=[]
    for path in sorted(base.glob('*/*/summary.json')):
        if not (path.parent/'manifest.json').is_file():continue
        summary=json.loads(path.read_text())
        rows.append({**summary,'path':path.parent.relative_to(base).as_posix()+'/index.html'})
    temp=base/('.index-'+uuid.uuid4().hex+'.tmp')
    write_file(temp,page(rows,True));os.replace(temp,base/'index.html')
    output=io.StringIO();writer=csv.writer(output)
    columns=['kind','number','subject','owner','status','created','completed','description','scope','approval_records','attachments','attachment_paths','path'];writer.writerow(columns)
    for row in rows:writer.writerow([("'"+str(row.get(k,''))) if str(row.get(k,'')).lstrip().startswith(('=','+','-','@')) else row.get(k,'') for k in columns])
    temp=base/('.csv-'+uuid.uuid4().hex+'.tmp');write_file(temp,('\ufeff'+output.getvalue()).encode());os.replace(temp,base/'archive.csv')

def lock(s):
    # This write serializes archive jobs on MySQL and SQLite before file/index work.
    if s.bind.dialect.name=='mysql':
        from sqlalchemy.dialects.mysql import insert
        stmt=insert(Setting).values(key='archive_job_lock',value='lock');s.execute(stmt.on_duplicate_key_update(value=uuid.uuid4().hex))
    else:
        from sqlalchemy.dialects.sqlite import insert
        s.execute(insert(Setting).values(key='archive_job_lock',value='lock').on_conflict_do_update(index_elements=['key'],set_={'value':uuid.uuid4().hex}))

def archive_one(engine,user_id=None):
    base,target=root()
    with Session(engine) as s:
        lock(s)
        item=next(candidates(s),None)
        if not item:return None
        kind,row,date=item
        s.refresh(row,with_for_update=True)
        date=completed(s,kind,row)
        if not date or date>cutoff():return None
        data,file_model,file_key=capture(s,kind,row,date)
        size_column=file_model.size if kind=='FAULT' else func.length(file_model.data)
        required=s.scalar(select(func.sum(size_column)).where(file_key==row.id)) or 0
        if shutil.disk_usage(base).free<required+len(json.dumps(data,default=str).encode())*2+100*1024*1024:
            raise HTTPException(409,'Insufficient archive disk space; online files retained')
        folder=kind+'/'+re.sub(r'[^A-Za-z0-9-]','',data['summary']['number'])
        dest=base/folder;temp=base/('.partial-'+uuid.uuid4().hex);temp.mkdir();(temp/'attachments').mkdir()
        meta=[]
        try:
            ids=s.scalars(select(file_model.id).where(file_key==row.id).order_by(file_model.id)).all()
            for file_id in ids:
                f=s.get(file_model,file_id)
                clean=re.sub(r'[^A-Za-z0-9._-]','_',f.filename).strip(' .') or 'attachment'
                suffix=Path(clean).suffix[:12]
                stem=clean[:-len(suffix)] if suffix else clean
                name=str(f.id)+'-'+stem[:80]+suffix
                relative='attachments/'+name;path=temp/relative
                if kind=='FAULT':
                    source=upload_dir()/f.storage_name
                    if not source.is_file():raise HTTPException(409,'Online attachment missing; archive stopped without cleanup')
                    expected=digest(source)
                    with source.open('rb') as src,path.open('wb') as out:shutil.copyfileobj(src,out);out.flush();os.fsync(out.fileno())
                else:
                    expected=hashlib.sha256(f.data).hexdigest()
                    write_file(path,f.data)
                size=path.stat().st_size;sha=digest(path)
                if sha!=expected:raise HTTPException(409,'Attachment copy verification failed; online files retained')
                with path.open('rb') as preview_file:signature=preview_file.read(16)
                attachment={'id':f.id,'filename':f.filename,'path':relative,'size':size,'sha256':sha,
                            'preview':signature.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'GIF87a',b'GIF89a')) or (signature[:4]==b'RIFF' and signature[8:12]==b'WEBP')}
                if kind=='FAULT':attachment.update(entry_id=f.entry_id,storage_name=f.storage_name)
                if kind=='CR':attachment.update(kind=f.kind,uploaded_by=f.uploaded_by,uploader=person(s,f.uploaded_by),created_at=str(f.created_at))
                if kind=='SR':attachment['mime']=f.mime
                if kind!='FAULT':attachment['version' if kind=='CR' else 'active']=f.version if kind=='CR' else bool(f.active)
                data['attachments'].append(attachment);meta.append(attachment)
            content=data['record'].get('content',{}) if kind=='CR' else data['record']
            data['summary'].update(description=content.get('background','') if kind=='CR' else content.get('description',''),scope=content.get('scope',''),approval_records='; '.join(str(h.get('actor',''))+' / '+str(h.get('action',''))+' / '+str(h.get('created_at',''))+' / '+str(h.get('comment',h.get('reason',''))) for h in data['history'] if h.get('action') in ('support','approve')),attachments='; '.join(f['filename'] for f in meta),attachment_paths='; '.join(folder+'/'+f['path'] for f in meta))
            write_file(temp/'summary.json',json.dumps(data['summary'],ensure_ascii=False,default=str,indent=2).encode())
            write_file(temp/'record.json',json.dumps(data,ensure_ascii=False,default=str,indent=2).encode())
            write_file(temp/'index.html',page(data))
            manifest=[{'path':p.relative_to(temp).as_posix(),'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(temp.rglob('*')) if p.is_file()]
            write_file(temp/'manifest.json',json.dumps(manifest,indent=2).encode());verify(temp)
            dest.parent.mkdir(exist_ok=True)
            if dest.exists():
                verify(dest)
                if (dest/'record.json').read_bytes()!=(temp/'record.json').read_bytes():raise HTTPException(409,'Existing archive differs; no online data was cleared')
                shutil.rmtree(temp)
            else:os.replace(temp,dest)
            build_index(base)
            archived=ArchiveRecord(kind=kind,record_id=row.id,number=data['summary']['number'],folder=folder,target=target,summary=json.dumps({k:v for k,v in data['summary'].items() if k in ('kind','number','subject','owner','status','created','completed')}),state='copied',copied_by=user_id)
            s.add(archived);s.flush()
            for f in meta:s.add(ArchiveFile(archive_id=archived.id,kind=kind,file_id=f['id'],path=f['path'],size=f['size'],sha256=f['sha256']))
            s.commit()
            return {'number':archived.number,'folder':folder,'state':'copied'}
        except Exception:
            s.rollback();shutil.rmtree(temp,ignore_errors=True);logger.exception('Archive copy failed; online attachments retained');raise

def purge_one(engine,user_id=None,*,export_id=None):
    if export_id is None and os.environ.get('ARCHIVE_PURGE_ENABLED','false').lower()!='true':raise HTTPException(409,'Online cleanup is disabled. Move and verify the archive on external storage first.')
    base,target=root()
    with Session(engine) as s:
        lock(s)
        archive=s.get(ArchiveRecord,export_id) if export_id is not None else s.scalar(select(ArchiveRecord).where(ArchiveRecord.state=='copied').order_by(ArchiveRecord.id))
        if not archive:return None
        if archive.target!=target:raise HTTPException(409,'Wrong archive disk; cleanup stopped')
        verify(base/archive.folder)
        files=s.scalars(select(ArchiveFile).where(ArchiveFile.archive_id==archive.id)).all()
        _,_,model=models()[archive.kind]
        paths=[]
        for file in files:
            row=s.get(model,file.file_id)
            if not row:raise HTTPException(409,'Attachment metadata changed; cleanup stopped')
            path=saved_path(s,archive.kind,file.file_id)
            if archive.kind=='FAULT':
                online=upload_dir()/row.storage_name
                if online.is_file() and digest(online)!=file.sha256:raise HTTPException(409,'Online attachment changed; cleanup stopped')
                paths.append(online)
            else:
                if row.data and (len(row.data)!=file.size or hashlib.sha256(row.data).hexdigest()!=file.sha256):raise HTTPException(409,'Online attachment changed; cleanup stopped')
                row.data=b''
        for path in paths:
            try:path.unlink(missing_ok=True)
            except OSError:
                logger.exception('Archive source cleanup failed; verified archive retained and cleanup can be retried')
                raise HTTPException(503,'Online file cleanup failed; verified archive is safe. Check disk permissions and retry.')
        archive.state='archived';archive.purged_by=user_id;archive.purged_at=now();s.commit()
        return {'number':archive.number,'state':'archived'}

_daily_retry_after=0

def daily(engine):
    global _daily_retry_after
    from zoneinfo import ZoneInfo
    from datetime import datetime
    if os.environ.get('ARCHIVE_ENABLED','false').lower()!='true':return
    date=datetime.now(ZoneInfo('Asia/Singapore'))
    if date.hour!=3 or time.monotonic()<_daily_retry_after:return
    _daily_retry_after=time.monotonic()+900
    with Session(engine) as s:
        row=s.get(Setting,'archive_last_run')
        if row and row.value==date.date().isoformat():return
    for _ in range(20):
        if not archive_one(engine):break
    with Session(engine) as s:
        row=s.get(Setting,'archive_last_run')
        if not row:row=Setting(key='archive_last_run');s.add(row)
        row.value=date.date().isoformat();s.commit()

def register(app):
    def admin(user):
        if user.role!='admin':raise HTTPException(403,'Administrator access required')
    @app.get('/api/archive/status')
    def status(user:User=Depends(current_user),s:Session=Depends(db)):
        admin(user)
        try:root();available=True
        except HTTPException:available=False
        return {'available':available,'eligible':sum(1 for _ in candidates(s)), 'records':[{'number':r.number,'kind':r.kind,'state':('offline' if r.location else r.state),'path':(r.location+' / ' if r.location else '')+r.folder+'/index.html'} for r in s.execute(select(ArchiveRecord.number,ArchiveRecord.kind,ArchiveRecord.state,ArchiveRecord.folder,ArchiveExport.location).outerjoin(ArchiveExport,ArchiveExport.archive_id==ArchiveRecord.id).order_by(ArchiveRecord.id.desc()))], 'purge_enabled':os.environ.get('ARCHIVE_PURGE_ENABLED','false').lower()=='true'}
    @app.post('/api/archive/run',dependencies=[Depends(write_guard)])
    def run(user:User=Depends(current_user)):
        admin(user)
        from app.main import engine
        return {'item':archive_one(engine,user.id)}
    @app.post('/api/archive/purge',dependencies=[Depends(write_guard)])
    def purge(user:User=Depends(current_user)):
        admin(user)
        from app.main import engine
        return {'item':purge_one(engine,user.id)}


def finish_export(engine,receipt):
    """Admin host helper: accept verified external-copy receipt, then clear local copies.

    Receipt is created only by the explicit Windows transfer command after remote
    hash verification. Local files are verified again before any online cleanup.
    """
    base,target=root()
    if receipt.get('target')!=target:raise HTTPException(409,'Export target marker does not match staging')
    location=receipt.get('location','')
    if not isinstance(location,str) or not location or len(location)>1000:raise HTTPException(422,'Invalid export location')
    done=[]
    for item in receipt.get('records',[]):
        with Session(engine) as s:
            archive=s.scalar(select(ArchiveRecord).where(ArchiveRecord.folder==item['folder'],ArchiveRecord.target==target))
            if not archive:raise HTTPException(409,'Unknown archive in export receipt')
            archive_id=archive.id
            exported=s.get(ArchiveExport,archive_id)
            folder=base/archive.folder
            if exported:
                if folder.exists() and exported.location==location:
                    verify(folder)
                    if digest(folder/'manifest.json')!=item['manifest_sha256']:raise HTTPException(409,'Export retry verification failed')
                    shutil.rmtree(folder)
                continue
            if not folder.resolve().is_relative_to(base.resolve()):raise HTTPException(409,'Invalid export path')
            verify(folder)
            if digest(folder/'manifest.json')!=item['manifest_sha256']:raise HTTPException(409,'External copy differs from staging; cleanup stopped')
        purge_one(engine,export_id=archive_id)
        with Session(engine) as s:
            lock(s)
            if not s.get(ArchiveExport,archive_id):s.add(ArchiveExport(archive_id=archive_id,location=location))
            s.commit()
        # Persist offline lookup before removing staging. A deletion failure is
        # safe: leave the extra verified copy for an administrator to remove.
        shutil.rmtree(folder)
        done.append(item['folder'])
    build_index(base)
    return done
