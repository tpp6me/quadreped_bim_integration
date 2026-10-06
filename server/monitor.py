"""Automatically analyze incoming samples and create deduplicated, unreviewed issues."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import uuid
from . import store,vision

_lock=threading.Lock()
_worker=None
_stop=threading.Event()
_progress={'state':'idle','processed':0,'total':0,'created':0,'errors':[],'current':''}
INTERVAL=15
RULE='dark-floor-cable-check-v2'
# Clip-level demonstration context, not localization or registered camera poses.
ZONES={'v01':'loading','v02':'production','v03':'production','v04':'production','v05':'loading','v06':'storage','v07':'storage','v08':'storage','v09':'assembly','v10':'storage'}

def status():
    with _lock:result=dict(_progress)
    result.update(modelsReady=vision.ready(),rule='Possible dark cable obstruction',sampleInterval=INTERVAL,automatic=True)
    return result

def bounds(box):return [box['x'],box['y'],box['x']+box['width'],box['y']+box['height']]

def persist(sample,result):
    """One transaction for provenance, automatic observation, and automatic issue."""
    source=Path(sample['path']);timestamp=store.now();created=[]
    key=hashlib.sha256(f"{sample['videoId']}:{sample['timestamp']}:{result['sourceSha256']}:{result['pipelineVersion']}".encode()).hexdigest()
    with store.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous=store.get(conn,'analyses',key)
        if previous:return []
        issues=[json.loads(row['payload']) for row in conn.execute('SELECT payload FROM issues')]
        for prediction in result['predictions']:
            # Suppress repeated views only within the same clip, rule, time neighbourhood,
            # and overlapping image region. Confirmed/dismissed findings are never reset.
            duplicate=next((i for i in issues if i.get('automation',{}).get('rule')==RULE and i['automation']['videoId']==sample['videoId'] and abs(i['automation']['lastSeen']-sample['timestamp'])<=INTERVAL*1.5 and vision.iou(bounds(prediction['box']),bounds(i['automation']['lastBox']))>.2),None)
            if duplicate:
                duplicate['automation']['lastSeen']=sample['timestamp'];duplicate['automation']['lastBox']=prediction['box']
                duplicate['automation']['sightings'].append({'timestamp':sample['timestamp'],'score':prediction['score'],'sourceSha256':result['sourceSha256']})
                duplicate['revision']+=1;duplicate['updatedAt']=timestamp;store.save(conn,'issues',duplicate)
                continue
            n=max([int(i['id'].split('-')[1]) for i in issues]+[0])+1;issue_id=f'FL-{n:03}';obs_id='AUTO-'+uuid.uuid4().hex[:12]
            evidence=store.DATA/'evidence'/f'{obs_id}.jpg';shutil.copyfile(source,evidence)
            element=ZONES[sample['videoId']]
            highlight={'label':prediction['label'],'method':'automatic-sam2','box':prediction['box'],'mask':prediction['mask'],'maskWidth':prediction['maskWidth'],'maskHeight':prediction['maskHeight'],'algorithm':'Grounding DINO + SAM 2.1 · automatic','sourceSha256':result['sourceSha256'],'sourceWidth':result['sourceWidth'],'sourceHeight':result['sourceHeight'],'reviewer':None,'reviewedAt':None,'generatedAt':result['generatedAt'],'generatedBy':'Fieldlink vision','detectionScore':prediction['score'],'maskQuality':prediction['maskQuality'],'models':result['models'],'strokes':[]}
            description='The system detected a possible dark cable in the lower part of the image. It may obstruct the floor route. Check the intended access route and whether protection or relocation is needed.'
            automation={'rule':RULE,'videoId':sample['videoId'],'timestamp':sample['timestamp'],'lastSeen':sample['timestamp'],'lastBox':prediction['box'],'score':prediction['score'],'modelLabel':prediction['label'],'pipelineVersion':result['pipelineVersion'],'models':result['models'],'generatedAt':result['generatedAt'],'cachedInference':result['cacheHit'],'sightings':[{'timestamp':sample['timestamp'],'score':prediction['score'],'sourceSha256':result['sourceSha256']}],'reason':'Dark-cable detector score at least 0.40; box centre in lower 45%; at least 80% of mask in lower half; dark-pixel fraction at least 20%; saturated-paint fraction at most 30%. Image-space screening, not calibrated floor geometry.'}
            o={'id':obs_id,'title':'Possible floor cable obstruction','videoId':sample['videoId'],'timestamp':sample['timestamp'],'start':max(0,sample['timestamp']-5),'end':sample['timestamp']+5,'elementId':element,'discipline':'Site Safety','priority':'Medium','description':description,'tags':['automatic','cable','wire','hose','floor','access'],'limitations':'Automatically flagged candidate. Verify object identity and route use; location is representative clip-level context.','status':'suggested','authoring':'Automatic detection + segmentation','reviewer':None,'reviewedAt':None,'thumbnail':f'/assets-data/evidence/{obs_id}.jpg','evidence':f'/assets-data/evidence/{obs_id}.jpg','revision':1,'history':[{'at':timestamp,'by':'Fieldlink vision','action':'auto flagged','note':automation['reason']}],'highlight':highlight,'automation':automation}
            issue={'id':issue_id,'guid':str(uuid.uuid4()),'observationId':obs_id,'title':o['title'],'description':description,'observationRevision':1,'observationReviewer':None,'observationReviewedAt':None,'elementId':element,'status':'needs_review','priority':'Medium','discipline':'Site Safety','assignee':'','dueDate':'','createdAt':timestamp,'createdBy':'Fieldlink vision','updatedAt':timestamp,'revision':1,'resolutionEvidence':'','automation':automation,'history':[{'at':timestamp,'by':'Fieldlink vision','action':'needs_review','note':'Created automatically from object detection and SAM 2 segmentation. No reviewer action was required.'}]}
            store.save(conn,'observations',o);store.save(conn,'issues',issue);issues.append(issue);created.append(issue_id)
        store.save(conn,'analyses',{'id':key,'videoId':sample['videoId'],'timestamp':sample['timestamp'],'sourceSha256':result['sourceSha256'],'models':result['models'],'pipelineVersion':result['pipelineVersion'],'generatedAt':result['generatedAt'],'processedAt':timestamp,'detections':len(result['predictions']),'createdIssues':created,'cachedInference':result['cacheHit']})
    return created

def samples():
    """Full-resolution video samples on a fixed schedule, plus the six indexed frames."""
    manifest=json.loads((store.DATA/'media.json').read_text())
    seed=[('v10',102),('v02',105),('v06',85),('v05',60),('v02',60),('v09',35)]
    scheduled=[(v['id'],t) for v in manifest for t in range(0,int(v['duration']),INTERVAL)]
    unique=list(dict.fromkeys(seed+scheduled));clips={v['id']:v for v in manifest}
    for video_id,t in unique:
        yield {'videoId':video_id,'timestamp':t,'video':clips[video_id]}

def source_frame(sample):
    media=Path(os.environ.get('FIELDLINK_MEDIA_DIR','/Users/praveen/Downloads/OneDrive_1_5-10-2026'))
    video=sample['video'];destination=store.DATA/'analysis-frames'/video['sha256'][:16]/f"{sample['timestamp']:03}.jpg"
    if destination.exists():return destination
    source=media/video['filename']
    if not source.is_file():raise RuntimeError(f"Source unavailable: {video['filename']}")
    destination.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['ffmpeg','-v','error','-ss',str(sample['timestamp']),'-i',str(source),'-frames:v','1','-q:v','2','-y',str(destination)],check=True,timeout=30,capture_output=True)
    return destination

def _run():
    global _progress
    entries=list(samples())
    with _lock:_progress.update(state='running',processed=0,total=len(entries),created=0,errors=[],current='Loading local vision models')
    try:
        for sample in entries:
            if _stop.is_set():break
            with _lock:_progress['current']=f"{sample['video']['filename']} · {sample['timestamp']}s"
            try:
                sample['path']=source_frame(sample)
                result=vision.analyze(sample['path']);created=persist(sample,result)
                with _lock:_progress['created']+=len(created)
            except Exception as exc:
                with _lock:_progress['errors'].append(f"{sample['videoId']} @ {sample['timestamp']}s: {exc}")
                # Fail clearly instead of inventing detections or silently falling back.
                if len(_progress['errors'])>=3:raise RuntimeError('Analysis stopped after three failed frames. See the run errors and retry.') from exc
            with _lock:_progress['processed']+=1
        with _lock:_progress['state']='stopped' if _stop.is_set() else 'completed';_progress['current']=''
    except Exception as exc:
        with _lock:_progress.update(state='failed',current=str(exc))

def start():
    global _worker
    with _lock:
        if _worker and _worker.is_alive():return False
        if not vision.ready():
            _progress.update(state='unavailable',current='Install vision dependencies and download the local models.');return False
        _stop.clear();_progress.update(state='starting',errors=[])
        _worker=threading.Thread(target=_run,name='fieldlink-auto-monitor',daemon=True);_worker.start()
    return True

def stop():_stop.set()
