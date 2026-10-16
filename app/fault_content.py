"""Fault visibility and allowlisted rich descriptions (no external resources)."""
from html import escape
from lxml import html,etree
from fastapi import HTTPException
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy import Column,Integer,String,Text,ForeignKey,select
from app.main import Base

class FaultContent(Base):
    __tablename__='fault_content'
    ticket_id=Column(Integer,ForeignKey('tickets.id'),primary_key=True)
    visibility=Column(String(10),nullable=False,default='Public')
    description_html=Column(Text().with_variant(LONGTEXT(),'mysql'),nullable=False,default='')

ALLOWED={'p','div','br','span','b','strong','i','em','u','s','ul','ol','li','table','thead','tbody','tfoot','tr','th','td','caption','blockquote','pre'}
BLOCKED={'script','style','iframe','object','embed','svg','math','template','head','link','meta','form','input','button','img','video','audio'}

def sanitize(value):
    if not value:return '',''
    try:root=html.fragment_fromstring(value,create_parent='div',parser=html.HTMLParser(no_network=True))
    except (etree.ParserError,ValueError):raise HTTPException(422,'Invalid formatted description')
    for node in list(root.iterdescendants()):
        if not isinstance(node.tag,str):
            if node.getparent() is not None:node.getparent().remove(node)
            continue
        if node.getparent() is None:continue
        tag=node.tag.lower()
        if tag in BLOCKED:node.drop_tree();continue
        if tag not in ALLOWED:node.drop_tag();continue
        attrs={}
        if tag in ('td','th'):
            for key in ('colspan','rowspan'):
                raw=node.get(key,'')
                if raw.isdigit() and 1<=int(raw)<=100:attrs[key]=raw
        node.attrib.clear();node.attrib.update(attrs)
    result=(escape(root.text or '')+''.join(html.tostring(n,encoding='unicode',method='html') for n in root))
    # Retain useful cell and paragraph boundaries in text exports and summaries.
    clone=html.fragment_fromstring(result or '',create_parent='div')
    for node in clone.iterdescendants():
        if node.tag in ('td','th'):node.tail='\t'+(node.tail or '')
        elif node.tag in ('p','div','tr','br','li'):node.tail='\n'+(node.tail or '')
    text=clone.text_content().strip()
    if len(result)>100000 or len(text)>20000:raise HTTPException(422,'Description is too large (20,000 text characters maximum)')
    return result,text

def metadata(session,id):
    # Session cache prevents one metadata query per list item.
    if 'fault_content' not in session.info:
        session.info['fault_content']={r.ticket_id:r for r in session.scalars(select(FaultContent))}
    row=session.info['fault_content'].get(id)
    return {'visibility':row.visibility if row else 'Public','description_html':row.description_html if row else ''}

def visible_filter(user):
    from app.main import Ticket
    return ~Ticket.id.in_(select(FaultContent.ticket_id).where(FaultContent.visibility=='Internal')) if user.role=='requester' else True
