"""Local, reviewer-guided foreground segmentation; no semantic detector."""
import base64
import hashlib
import threading
from io import BytesIO
from typing import Literal
import cv2
import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field, model_validator
from . import store

SEGMENT_LOCK=threading.Lock()

class Box(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)
    width:float=Field(ge=.005,le=.99)
    height:float=Field(ge=.005,le=.99)
    @model_validator(mode='after')
    def bounds(self):
        if self.x+self.width>1.000001 or self.y+self.height>1.000001:
            raise ValueError('Keep the selection inside the image.')
        return self

class Point(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    x:float=Field(ge=0,le=1)
    y:float=Field(ge=0,le=1)

class Stroke(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    kind:Literal['include','exclude']
    width:float=Field(ge=.001,le=.04)
    points:list[Point]=Field(min_length=1,max_length=1000)

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    label:str=Field(min_length=1,max_length=100)
    method:Literal['grabcut','manual-box']
    box:Box
    strokes:list[Stroke]=Field(default_factory=list,max_length=40)

def generate(key,selection):
    path=store.DATA/'evidence'/f'{key}.jpg'
    raw=path.read_bytes()
    original=Image.open(BytesIO(raw)).convert('RGB')
    image=original.copy();image.thumbnail((1280,720))
    w,h=image.size;b=selection.box
    x,y=int(b.x*w),int(b.y*h);right,bottom=min(w,int((b.x+b.width)*w)),min(h,int((b.y+b.height)*h))
    if right-x<3 or bottom-y<3:raise ValueError('Draw a larger selection.')
    result=selection.model_dump()
    result.update(sourceSha256=hashlib.sha256(raw).hexdigest(),sourceWidth=original.width,sourceHeight=original.height)
    if selection.method=='manual-box':
        result.update(mask=None,algorithm='Reviewer-drawn box')
        return result
    pixels=cv2.cvtColor(np.array(image),cv2.COLOR_RGB2BGR)
    mask=np.zeros((h,w),np.uint8)
    has_include=any(s.kind=='include' for s in selection.strokes)
    mask[y:bottom,x:right]=cv2.GC_PR_BGD if has_include else cv2.GC_PR_FGD
    for stroke in selection.strokes:
        pts=np.array([[round(p.x*(w-1)),round(p.y*(h-1))] for p in stroke.points],dtype=np.int32)
        value=cv2.GC_FGD if stroke.kind=='include' else cv2.GC_BGD
        thickness=max(1,round(stroke.width*w))
        if len(pts)==1:cv2.circle(mask,tuple(pts[0]),max(1,thickness//2),value,-1)
        else:cv2.polylines(mask,[pts],False,value,thickness)
    # The box is a hard boundary, including when a stroke leaves it.
    inside=np.zeros((h,w),bool);inside[y:bottom,x:right]=True;mask[~inside]=cv2.GC_BGD
    if has_include and not np.any(mask==cv2.GC_FGD):raise ValueError('Add an include stroke inside the box.')
    try:
        with SEGMENT_LOCK:
            cv2.setRNGSeed(42)
            cv2.grabCut(pixels,mask,None,np.zeros((1,65),np.float64),np.zeros((1,65),np.float64),5,cv2.GC_INIT_WITH_MASK)
    except cv2.error as exc:raise ValueError('Could not segment this selection. Adjust the box or add an include stroke.') from exc
    foreground=np.isin(mask,[cv2.GC_FGD,cv2.GC_PR_FGD])
    if not foreground.any():raise ValueError('No foreground found. Add an include stroke over the item, or save a manual box.')
    # Transparent amber fill with a brighter contour; keep source pixels separate.
    rgba=np.zeros((h,w,4),np.uint8);rgba[foreground]=(255,182,39,100)
    edge=cv2.dilate(foreground.astype(np.uint8),np.ones((3,3),np.uint8))-foreground.astype(np.uint8)
    rgba[edge.astype(bool)]=(255,199,65,240)
    out=BytesIO();Image.fromarray(rgba).save(out,format='PNG')
    result.update(mask=base64.b64encode(out.getvalue()).decode(),algorithm='OpenCV GrabCut · reviewer-guided',maskWidth=w,maskHeight=h)
    return result

def annotated_image(observation):
    image=Image.open(store.DATA/'evidence'/f"{observation['id']}.jpg").convert('RGBA')
    highlight=observation.get('highlight')
    if not highlight:return image.convert('RGB')
    if highlight.get('mask'):
        overlay=Image.open(BytesIO(base64.b64decode(highlight['mask']))).convert('RGBA').resize(image.size,Image.Resampling.NEAREST)
        image=Image.alpha_composite(image,overlay)
    draw=ImageDraw.Draw(image);b=highlight['box'];w,h=image.size
    bounds=(round(b['x']*w),round(b['y']*h),round((b['x']+b['width'])*w),round((b['y']+b['height'])*h))
    draw.rectangle(bounds,outline='#ffc741',width=4)
    return image.convert('RGB')
