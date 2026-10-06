from contextlib import asynccontextmanager
from datetime import date
import json
import os
from pathlib import Path
from typing import Literal
import uuid
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict
from . import store
from .highlights import Selection, generate
from . import monitor

ROOT=store.ROOT
MEDIA=Path(os.environ.get('FIELDLINK_MEDIA_DIR','/Users/praveen/Downloads/OneDrive_1_5-10-2026'))
@asynccontextmanager
async def lifespan(app):
    store.seed()
    if os.environ.get('FIELDLINK_AUTORUN','1')=='1':monitor.start()
    yield
    monitor.stop()
app=FastAPI(title='Fieldlink local demo',lifespan=lifespan)

@app.middleware('http')
async def local_mutations(request:Request,call_next):
    if request.method in ('POST','PATCH','DELETE','PUT'):
        origin=request.headers.get('origin')
        if origin and urlparse(origin).netloc != request.headers.get('host'):
            return JSONResponse({'detail':'Cross-origin writes are not allowed.'},status_code=403)
    return await call_next(request)

def read(name):return json.loads((store.DATA/name).read_text())
def fail(message,status=422):raise HTTPException(status_code=status,detail=message)
def require_record(conn,table,key):
    record=store.get(conn,table,key)
    if not record:fail('Record not found',404)
    return record
def actor(value):
    if not value.strip():fail('Enter a reviewer name.')
    return value.strip()
class StrictBody(BaseModel):model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Review(StrictBody):
    revision:int
    reviewer:str=Field(min_length=1,max_length=100)
    status:Literal['confirmed','dismissed','suggested']
    description:str=Field(min_length=10,max_length=4000)
    title:str=Field(min_length=3,max_length=180)
    note:str=Field(default='',max_length=2000)
class HighlightUpdate(StrictBody):
    revision:int
    reviewer:str=Field(min_length=1,max_length=100)
    selection:Selection|None
class CreateIssue(StrictBody):
    observationId:str
    reviewer:str=Field(min_length=1,max_length=100)
    discipline:Literal['Structural','Architectural','MEP','Site Safety','General']
    priority:Literal['High','Medium','Low']
class IssueUpdate(StrictBody):
    revision:int
    reviewer:str=Field(min_length=1,max_length=100)
    status:Literal['needs_review','dismissed','open','assigned','resolved','closed']
    assignee:str=Field(default='',max_length=150)
    dueDate:str=Field(default='',max_length=10)
    note:str=Field(default='',max_length=2000)
    resolutionEvidence:str=Field(default='',max_length=1000)
    priority:Literal['High','Medium','Low']
    discipline:Literal['Structural','Architectural','MEP','Site Safety','General']

@app.get('/api/health')
def health():return {'ok':True,'mediaAvailable':MEDIA.is_dir(),'mode':'local-demo'}
@app.get('/api/project')
def project():
    model=read('model.json');videos=read('media.json')
    for video in videos:video['available']=(MEDIA/video['filename']).is_file()
    return {'model':model,'videos':videos,'observations':store.all_records('observations'),'issues':store.all_records('issues'),'exports':store.all_records('exports'),'analysis':monitor.status(),'integration':{'bcf':'2.1','receivingTool':'Not yet independently verified'},'project':{'name':'Northworks Industrial Facility','scenario':'Industrial handover · representative scenario','level':'L00 · Ground Floor'}}

@app.post('/api/analysis/run',status_code=202)
def start_analysis():
    if not monitor.vision.ready():fail('Download local vision models with scripts/prepare_vision.py.',503)
    monitor.start();return monitor.status()

@app.get('/api/analysis')
def analysis_status():return monitor.status()

@app.get('/api/search')
def search(q:str=''):
    import re
    terms=[t for t in re.findall(r'\w+',q.lower()) if t not in {'the','on','in','a','an','of','show','find','me','with'}]
    results=[]
    for o in store.all_records('observations'):
        text=(' '.join(o['tags'])+' '+o['title']+' '+o['description']).lower()
        if not terms or all(t.rstrip('s') in text for t in terms):results.append(o)
    return {'mode':'curated index','results':results}

@app.patch('/api/observations/{key}')
def review(key:str,body:Review):
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE');o=require_record(conn,'observations',key)
        if body.revision!=o['revision']:fail('This observation changed. Refresh before saving.',409)
        if body.status!='confirmed' and any(i['observationId']==key for i in store.all_records('issues')):fail('This observation has an issue. Retain its confirmed evidence record.',409)
        who=actor(body.reviewer);timestamp=store.now()
        o.update(title=body.title.strip(),description=body.description.strip(),status=body.status,reviewer=who,reviewedAt=timestamp,revision=o['revision']+1)
        o['history'].append({'at':timestamp,'by':who,'action':body.status,'note':body.note,'description':o['description']})
        store.save(conn,'observations',o)
    return o

@app.post('/api/issues',status_code=201)
def create_issue(body:CreateIssue):
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE');o=require_record(conn,'observations',body.observationId)
        if o['status']!='confirmed':fail('Confirm the observation before creating an issue.')
        rows=[json.loads(r['payload']) for r in conn.execute('SELECT payload FROM issues')]
        if any(i['observationId']==o['id'] for i in rows):fail('An issue already exists for this observation.',409)
        who=actor(body.reviewer);timestamp=store.now()
        issue={'id':f'FL-{len(rows)+1:03}','guid':str(uuid.uuid4()),'observationId':o['id'],'title':o['title'],'description':o['description'],'observationRevision':o['revision'],'observationReviewer':o['reviewer'],'observationReviewedAt':o['reviewedAt'],'elementId':o['elementId'],'status':'open','priority':body.priority,'discipline':body.discipline,'assignee':'','dueDate':'','createdAt':timestamp,'createdBy':who,'updatedAt':timestamp,'revision':1,'resolutionEvidence':'','history':[{'at':timestamp,'by':who,'action':'open','note':'Created from a confirmed observation.'}]}
        store.save(conn,'issues',issue)
    return issue

@app.post('/api/observations/{key}/segment')
def segment(key:str,body:Selection):
    with store.connect() as conn:require_record(conn,'observations',key)
    try:return generate(key,body)
    except FileNotFoundError:fail('The source evidence image is unavailable.',404)
    except ValueError as exc:fail(str(exc))

@app.patch('/api/observations/{key}/highlight')
def save_highlight(key:str,body:HighlightUpdate):
    with store.connect() as conn:require_record(conn,'observations',key)
    try:highlight=generate(key,body.selection) if body.selection else None
    except FileNotFoundError:fail('The source evidence image is unavailable.',404)
    except ValueError as exc:fail(str(exc))
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE');o=require_record(conn,'observations',key)
        if body.revision!=o['revision']:fail('This observation changed. Reopen the highlight editor before saving.',409)
        who=actor(body.reviewer);timestamp=store.now()
        if highlight:highlight.update(reviewer=who,reviewedAt=timestamp)
        o.update(highlight=highlight,revision=o['revision']+1)
        o['history'].append({'at':timestamp,'by':who,'action':'highlight confirmed' if highlight else 'highlight removed','note':f"{highlight['label']} · {highlight['algorithm']}" if highlight else 'Removed the evidence highlight.'})
        store.save(conn,'observations',o)
    return o

@app.patch('/api/issues/{key}')
def update_issue(key:str,body:IssueUpdate):
    transitions={'needs_review':{'needs_review','open','dismissed'},'dismissed':{'dismissed','needs_review'},'open':{'open','assigned'},'assigned':{'assigned','resolved','open'},'resolved':{'resolved','closed','assigned'},'closed':{'closed','open'}}
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE');issue=require_record(conn,'issues',key)
        if issue['revision']!=body.revision:fail('This issue changed. Refresh before saving.',409)
        if body.status not in transitions[issue['status']]:fail('Follow the issue workflow: open, assigned, resolved, verified/closed.')
        who=actor(body.reviewer)
        if issue['status']=='needs_review' and body.status in ('open','dismissed') and not body.note.strip():fail('Add a review note when confirming or dismissing an automatic issue.')
        if body.dueDate:
            try:date.fromisoformat(body.dueDate)
            except ValueError:fail('Use a valid due date.')
        if body.status in ('assigned','resolved','closed') and (not body.assignee.strip() or not body.dueDate):fail('Assignment requires a responsible party and due date.')
        if body.status in ('resolved','closed') and (not body.resolutionEvidence.strip() or not body.note.strip()):fail('Resolution and verification require supporting evidence and a note.')
        if body.status=='open' and issue['status']=='closed' and not body.note.strip():fail('Reopening requires a reason.')
        timestamp=store.now();prior_status=issue['status']
        issue.update(status=body.status,assignee=body.assignee.strip(),dueDate=body.dueDate,priority=body.priority,discipline=body.discipline,resolutionEvidence=body.resolutionEvidence.strip(),updatedAt=timestamp,revision=issue['revision']+1)
        issue['history'].append({'at':timestamp,'by':who,'action':body.status,'note':body.note.strip(),'resolutionEvidence':body.resolutionEvidence.strip()})
        if issue.get('automation') and prior_status=='needs_review' and body.status in ('open','dismissed'):
            o=require_record(conn,'observations',issue['observationId'])
            o.update(status='confirmed' if body.status=='open' else 'dismissed',reviewer=who,reviewedAt=timestamp,revision=o['revision']+1)
            if o.get('highlight'):o['highlight'].update(reviewer=who,reviewedAt=timestamp,reviewDecision=o['status'])
            o['history'].append({'at':timestamp,'by':who,'action':o['status'],'note':body.note})
            issue.update(observationReviewer=who,observationReviewedAt=timestamp,observationRevision=o['revision'])
            store.save(conn,'observations',o)
        store.save(conn,'issues',issue)
    return issue

@app.get('/media/{video_id}')
def media(video_id:str):
    video=next((v for v in read('media.json') if v['id']==video_id),None)
    if not video:fail('Video not found',404)
    path=MEDIA/video['filename']
    if not path.is_file():fail('Source video is unavailable. Set FIELDLINK_MEDIA_DIR to its folder.',404)
    return FileResponse(path,media_type='video/mp4',headers={'Cache-Control':'private, max-age=3600'})

@app.get('/api/exports/{kind}')
def export(kind:Literal['pdf','bcf','bundle','ifc']):
    if kind=='ifc':return FileResponse(store.DATA/'representative.ifc',filename='representative.ifc',media_type='application/octet-stream')
    from .exports import make_export
    issues=store.all_records('issues')
    if not issues:fail('Create at least one issue before exporting the punch list.')
    content,filename,mime=make_export(kind,issues,store.all_records('observations'),read('model.json'),read('media.json'))
    with store.connect() as conn:store.save(conn,'exports',{'id':str(uuid.uuid4()),'kind':kind,'filename':filename,'createdAt':store.now(),'issueIds':[i['id'] for i in issues],'bcfVersion':'2.1','receivingTool':'Not yet independently verified'})
    return Response(content,media_type=mime,headers={'Content-Disposition':f'attachment; filename="{filename}"'})

# Expose derived presentation assets only, never the database or arbitrary local files.
for folder in ['frames','evidence']:
    (store.DATA/folder).mkdir(exist_ok=True,parents=True)
    app.mount(f'/assets-data/{folder}',StaticFiles(directory=store.DATA/folder),name=folder)
@app.get('/api/explainer')
def explainer():return FileResponse(ROOT/'docs/robodog-construction-monitoring.html')
if (ROOT/'dist').exists():app.mount('/',StaticFiles(directory=ROOT/'dist',html=True),name='frontend')
if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=int(os.environ.get('FIELDLINK_PORT','8000')))
