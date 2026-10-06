"""Offline object detection and segmentation. No hand-drawn geometry is used."""
import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import threading
import time
import uuid
import cv2
import numpy as np
from PIL import Image
from . import store

MODEL_DIR=store.DATA/'models'
CACHE_DIR=Path(os.environ.get('FIELDLINK_ANALYSIS_CACHE',str(store.DATA/'analysis-cache')))
PIPELINE_VERSION='dark-floor-cable-v2'
PROMPT='a black cable.'
THRESHOLD=.4
_engine=None
_lock=threading.Lock()

def ready():
    return (MODEL_DIR/'registry.json').is_file() and all((MODEL_DIR/k/'model.safetensors').is_file() for k in ['detector','segmenter'])

class Engine:
    def __init__(self):
        os.environ.setdefault('HF_HUB_OFFLINE','1')
        os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
        os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
        import torch
        from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection,Sam2Model,Sam2Processor
        self.torch=torch
        torch.set_num_threads(4)
        self.device=os.environ.get('FIELDLINK_VISION_DEVICE','cpu')
        self.detector_processor=AutoProcessor.from_pretrained(MODEL_DIR/'detector',local_files_only=True)
        self.detector=AutoModelForZeroShotObjectDetection.from_pretrained(MODEL_DIR/'detector',local_files_only=True).eval().to(self.device)
        self.detector.config.disable_custom_kernels=True
        self.segment_processor=Sam2Processor.from_pretrained(MODEL_DIR/'segmenter',local_files_only=True)
        self.segmenter=Sam2Model.from_pretrained(MODEL_DIR/'segmenter',local_files_only=True).eval().to(self.device)

    def infer(self,image):
        inputs=self.detector_processor(images=image,text=PROMPT,return_tensors='pt').to(self.device)
        with self.torch.inference_mode():outputs=self.detector(**inputs)
        detections=self.detector_processor.post_process_grounded_object_detection(outputs,inputs.input_ids,threshold=THRESHOLD,text_threshold=.2,target_sizes=[(image.height,image.width)])[0]
        boxes=detections['boxes'].cpu().numpy();scores=detections['scores'].cpu().numpy();labels=detections['text_labels']
        candidates=[]
        for box,score,label in sorted(zip(boxes,scores,labels),key=lambda row:float(row[1]),reverse=True):
            x1,y1,x2,y2=box.tolist();x1=max(0,x1);y1=max(0,y1);x2=min(image.width,x2);y2=min(image.height,y2)
            if not any(word in label for word in ['cable','wire','hose']):continue
            if (y1+y2)/2<image.height*.55 or x2-x1<8 or y2-y1<3:continue
            bounds=[x1,y1,x2,y2]
            if any(iou(bounds,c['bounds'])>.4 for c in candidates):continue
            candidates.append({'bounds':bounds,'score':float(score),'label':label})
        if not candidates:return []
        candidates=candidates[:4]
        inputs=self.segment_processor(images=image,input_boxes=[[c['bounds'] for c in candidates]],return_tensors='pt').to(self.device)
        with self.torch.inference_mode():outputs=self.segmenter(**inputs,multimask_output=False)
        masks=self.segment_processor.post_process_masks(outputs.pred_masks.cpu(),inputs['original_sizes'].cpu())[0]
        result=[]
        hsv=cv2.cvtColor(np.array(image),cv2.COLOR_RGB2HSV)
        for n,c in enumerate(candidates):
            mask=masks[n,0].numpy().astype(bool)
            if mask.sum()<20:continue
            # A screening rule, not a calibrated floor plane or a hazard classifier.
            lower_fraction=float(mask[int(image.height*.5):].sum()/mask.sum())
            if lower_fraction<.8:continue
            values=hsv[mask]
            dark_fraction=float(((values[:,2]<120)&(values[:,1]<110)).mean())
            paint_fraction=float(((values[:,1]>100)&(values[:,2]>100)).mean())
            # Avoid common painted-route false positives for this dark-cable check.
            if dark_fraction<.2 or paint_fraction>.3:continue
            b=c.pop('bounds');c['box']={'x':b[0]/image.width,'y':b[1]/image.height,'width':(b[2]-b[0])/image.width,'height':(b[3]-b[1])/image.height}
            c.update(mask=encode_mask(mask),maskWidth=image.width,maskHeight=image.height,maskQuality=float(outputs.iou_scores[0,n,0].cpu()),lowerImageFraction=lower_fraction,darkPixelFraction=dark_fraction,paintPixelFraction=paint_fraction)
            result.append(c)
        return result

def iou(a,b):
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union if union else 0

def encode_mask(mask):
    rgba=np.zeros((*mask.shape,4),np.uint8);rgba[mask]=(255,182,39,105)
    edge=cv2.dilate(mask.astype(np.uint8),np.ones((3,3),np.uint8))-mask.astype(np.uint8)
    rgba[edge.astype(bool)]=(255,199,65,245)
    out=BytesIO();Image.fromarray(rgba).save(out,format='PNG');return base64.b64encode(out.getvalue()).decode()

def analyze(path,force=False):
    global _engine
    if not ready():raise RuntimeError('Vision models are missing. Run scripts/prepare_vision.py after installing requirements-vision.txt.')
    raw=Path(path).read_bytes();digest=hashlib.sha256(raw).hexdigest();registry=json.loads((MODEL_DIR/'registry.json').read_text())
    signature=hashlib.sha256(json.dumps({'source':digest,'models':registry,'pipeline':PIPELINE_VERSION,'prompt':PROMPT,'threshold':THRESHOLD},sort_keys=True).encode()).hexdigest()
    cache=CACHE_DIR/f'{signature}.json'
    with _lock:
        if cache.exists() and not force:
            result=json.loads(cache.read_text());result['cacheHit']=True;return result
        start=time.monotonic()
        if _engine is None:_engine=Engine()
        image=Image.open(BytesIO(raw)).convert('RGB')
        predictions=_engine.infer(image)
        result={'sourceSha256':digest,'sourceWidth':image.width,'sourceHeight':image.height,'models':registry,'pipelineVersion':PIPELINE_VERSION,'prompt':PROMPT,'threshold':THRESHOLD,'generatedAt':store.now(),'inferenceSeconds':round(time.monotonic()-start,3),'predictions':predictions,'cacheHit':False}
        CACHE_DIR.mkdir(parents=True,exist_ok=True);temp=cache.with_suffix('.'+uuid.uuid4().hex+'.tmp');temp.write_text(json.dumps(result));temp.replace(cache)
        return result
