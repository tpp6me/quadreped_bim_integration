"""Portable PDF/BCF exports. Camera and snapshot share one model coordinate system."""
from io import BytesIO
from functools import lru_cache
import json
import uuid
import zipfile
from xml.sax.saxutils import escape
import numpy as np
from PIL import Image, ImageColor, ImageDraw
from lxml import etree as ET
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage, PageBreak, Table, TableStyle
from .store import DATA, now
from .highlights import annotated_image

def clock(seconds):return f'{int(seconds)//60:02}:{int(seconds)%60:02}'
def sub(parent,name,text=None,**attrs):
    child=ET.SubElement(parent,name,**attrs)
    if text is not None:child.text=str(text)
    return child
def xml(root):return ET.tostring(root,xml_declaration=True,encoding='UTF-8',pretty_print=True)
def validate(root,schema):ET.XMLSchema(ET.parse(str(DATA/'schemas'/schema))).assertValid(root)
def vectors():
    target=np.array([24.,16.,1.]);position=np.array([69.,-39.,51.])
    direction=target-position;direction/=np.linalg.norm(direction)
    right=np.cross(direction,[0,0,1]);right/=np.linalg.norm(right)
    up=np.cross(right,direction)
    return position,direction,right,up
def snapshot(model,selected):
    position,direction,right,up=vectors();width,height=1000,650;scale=52.
    im=Image.new('RGB',(width,height),'#f1f2ea');draw=ImageDraw.Draw(im)
    def project(v):
        relative=np.array(v)-position
        return (width/2+float(relative@right)*height/scale,height/2-float(relative@up)*height/scale)
    pixels=np.full((height,width,3),(241,242,234),dtype=np.uint8)
    zbuffer=np.full((height,width),np.inf)
    for element in model['elements']:
        if element['category']=='Envelope':continue
        verts=np.array(element['vertices']).reshape(-1,3)
        for tri in np.array(element['indices']).reshape(-1,3):
            points=verts[tri];normal=np.cross(points[1]-points[0],points[2]-points[0]);normal/=max(np.linalg.norm(normal),1e-9)
            if normal@direction>=0:continue
            color=ImageColor.getrgb('#e8ae4e' if element['id']==selected else element['color'])
            shade=.78+.22*abs(float(normal[2]));color=tuple(int(c*shade) for c in color)
            screen=np.array([project(p) for p in points]);depths=(points-position)@direction
            lo=np.maximum(np.floor(screen.min(axis=0)).astype(int),[0,0]);hi=np.minimum(np.ceil(screen.max(axis=0)).astype(int),[width-1,height-1])
            if np.any(hi<lo):continue
            (ax,ay),(bx,by),(cx,cy)=screen;den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
            if abs(den)<1e-8:continue
            yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];xx=xx+.5;yy=yy+.5
            a=((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den;b=((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den;c=1-a-b
            depth=a*depths[0]+b*depths[1]+c*depths[2]
            region=zbuffer[lo[1]:hi[1]+1,lo[0]:hi[0]+1]
            mask=(a>=-1e-6)&(b>=-1e-6)&(c>=-1e-6)&(depth<region)
            region[mask]=depth[mask];pixels[lo[1]:hi[1]+1,lo[0]:hi[0]+1][mask]=color
    im=Image.fromarray(pixels);draw=ImageDraw.Draw(im)
    draw.text((24,20),'FIELDLINK / REPRESENTATIVE BIM VIEW',fill='#18392e')
    draw.text((24,height-30),f'Selected: {selected} | Z-up, metres | manually mapped evidence',fill='#18392e')
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()
def evidence_bytes(o,highlighted=False):
    path=DATA/'evidence'/f"{o['id']}.jpg"
    if not path.exists():path=DATA/'frames'/o['videoId']/f"{o['timestamp']:03}.jpg"
    im=annotated_image(o) if highlighted and o.get('highlight') else Image.open(path).convert('RGB');draw=ImageDraw.Draw(im)
    draw.rectangle((0,im.height-32,im.width,im.height),fill='#18392e')
    draw.text((12,im.height-23),f"{o['id']} | {o['videoId']} | clip {clock(o['timestamp'])} | capture date unknown",fill='white')
    out=BytesIO();im.save(out,format='PNG');return out.getvalue()

@lru_cache(maxsize=32)
def cached_snapshot(model_json,selected):
    return snapshot(json.loads(model_json),selected)
def highlight_provenance(h):
    if h.get('reviewer'):return f"Highlight reviewed by {h['reviewer']} at {h['reviewedAt']} | {h.get('reviewDecision','confirmed')}"
    return f"Highlight generated automatically by {h.get('generatedBy','Fieldlink vision')} at {h.get('generatedAt','unknown')} | Human review pending"

def make_bcf(issues,observations,model,videos):
    out=BytesIO();obs={o['id']:o for o in observations};elements={e['id']:e for e in model['elements']};clips={v['id']:v for v in videos}
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        version=ET.Element('Version',VersionId='2.1');validate(version,'version.xsd');archive.writestr('bcf.version',xml(version))
        for issue in issues:
            o=obs[issue['observationId']];e=elements[issue['elementId']];video=clips[o['videoId']];topic_id=issue['guid'];view_id=str(uuid.uuid5(uuid.UUID(topic_id),'view'))
            root=ET.Element('Markup');header=sub(root,'Header');file=sub(header,'File',IfcProject=model['projectId'],isExternal='true');sub(file,'Filename','representative.ifc')
            topic=sub(root,'Topic',Guid=topic_id,TopicType='Issue',TopicStatus=issue['status'])
            sub(topic,'Title',f"{issue['id']} · {issue['title']}");sub(topic,'Priority',issue['priority']);sub(topic,'Labels',issue['discipline']);sub(topic,'Labels','Representative model');sub(topic,'CreationDate',issue['createdAt']);sub(topic,'CreationAuthor',issue['createdBy']);sub(topic,'ModifiedDate',issue['updatedAt']);sub(topic,'ModifiedAuthor',issue['history'][-1]['by'])
            if issue['dueDate']:sub(topic,'DueDate',issue['dueDate']+'T00:00:00Z')
            if issue['assignee']:sub(topic,'AssignedTo',issue['assignee'])
            sub(topic,'Stage','Handover demonstration')
            sub(topic,'Description',f"{issue['description']}\nSource: {video['filename']} @ {clock(o['timestamp'])}. Capture date unknown.\nLocation: {e['name']}; grid {e['grid']}; model {model['version']}; IFC {e['globalId']}.\nManually mapped, illustrative location. Observation reviewed by {(issue.get('observationReviewer') or 'Human review pending')} at {(issue.get('observationReviewedAt') or 'Not yet reviewed')}.\nResolution evidence: {issue.get('resolutionEvidence') or 'None supplied'}")
            doc=sub(topic,'DocumentReference',Guid=str(uuid.uuid5(uuid.UUID(topic_id),'evidence')),isExternal='false');sub(doc,'ReferencedDocument','evidence.png');sub(doc,'Description',f"Source frame: {video['filename']} @ {clock(o['timestamp'])}; not a calibrated model viewpoint")
            if o.get('highlight'):
                h=o['highlight']
                for name,description in [('highlighted.png',f"Highlight: {h['label']} | {h['algorithm']} | {highlight_provenance(h)}. Candidate finding; hazard not verified."),('source-original.jpg','Unmodified source evidence frame'),('highlight.json','Selection, segmentation mask, reviewer, and source image hash')]:
                    ref=sub(topic,'DocumentReference',Guid=str(uuid.uuid5(uuid.UUID(topic_id),name)),isExternal='false');sub(ref,'ReferencedDocument',name);sub(ref,'Description',description)
            for n,event in enumerate(issue['history']):
                comment=sub(root,'Comment',Guid=str(uuid.uuid5(uuid.UUID(topic_id),f'comment-{n}')));sub(comment,'Date',event['at']);sub(comment,'Author',event['by']);sub(comment,'Comment',f"{event['action']}: {event['note']}\n{event.get('resolutionEvidence','')}")
            view=sub(root,'Viewpoints',Guid=view_id);sub(view,'Viewpoint','viewpoint.bcfv');sub(view,'Snapshot','snapshot.png');sub(view,'Index',0)
            validate(root,'markup.xsd')
            vis=ET.Element('VisualizationInfo',Guid=view_id);components=sub(vis,'Components');sub(components,'ViewSetupHints',SpacesVisible='true',SpaceBoundariesVisible='false',OpeningsVisible='false');selection=sub(components,'Selection');sub(selection,'Component',IfcGuid=e['globalId']);visibility=sub(components,'Visibility',DefaultVisibility='true');exceptions=sub(visibility,'Exceptions')
            for item in model['elements']:
                if item['category']=='Envelope':sub(exceptions,'Component',IfcGuid=item['globalId'])
            color=sub(sub(components,'Coloring'),'Color',Color='E8AE4E');sub(color,'Component',IfcGuid=e['globalId'])
            camera=sub(vis,'OrthogonalCamera');position,direction,_,up=vectors()
            for name,vec in [('CameraViewPoint',position),('CameraDirection',direction),('CameraUpVector',up)]:
                point=sub(camera,name)
                for axis,val in zip('XYZ',vec):sub(point,axis,float(val))
            sub(camera,'ViewToWorldScale',52.);validate(vis,'visinfo.xsd')
            archive.writestr(f'{topic_id}/markup.bcf',xml(root));archive.writestr(f'{topic_id}/viewpoint.bcfv',xml(vis));archive.writestr(f'{topic_id}/snapshot.png',cached_snapshot(json.dumps(model,sort_keys=True),e['id']));archive.writestr(f'{topic_id}/evidence.png',evidence_bytes(o))
            if o.get('highlight'):
                archive.writestr(f'{topic_id}/highlighted.png',evidence_bytes(o,True))
                archive.write(DATA/'evidence'/f"{o['id']}.jpg",f'{topic_id}/source-original.jpg')
                archive.writestr(f'{topic_id}/highlight.json',json.dumps(o['highlight'],indent=2))
    return out.getvalue()

def make_pdf(issues,observations,model,videos):
    out=BytesIO();styles=getSampleStyleSheet();styles['Title'].textColor=colors.HexColor('#18392e');styles['BodyText'].fontSize=9;styles['BodyText'].leading=13
    obs={o['id']:o for o in observations};elements={e['id']:e for e in model['elements']};clips={v['id']:v for v in videos}
    def p(text,style='BodyText'):return Paragraph(escape(str(text)),styles[style])
    flow=[p('FIELDLINK / HANDOVER PUNCH LIST','Title'),p(model['name'],'Heading2'),p(f'Exported {now()} | Model v{model["version"]} | {len(issues)} issues'),Spacer(1,14),p('Representative industrial handover scenario. Source footage shows an operating factory. Locations are manually mapped and illustrative. Capture dates are unknown. This report does not establish construction progress or commissioning acceptance.'),Spacer(1,14)]
    for i in issues:flow.append(p(f'{i["id"]} — {i["title"]} / {i["status"]} / {i["priority"]}'))
    flow.extend([Spacer(1,20),p('Interoperability: BCF 2.1 schema-validated export. Independent receiving-tool verification remains pending. The companion IFC must be loaded in the receiving application.'),p('Reviewer and assignment names are entered for this local demonstration; no authenticated identity or external notifications are implied.')])
    for issue in issues:
        o=obs[issue['observationId']];e=elements[issue['elementId']];video=clips[o['videoId']]
        flow.extend([PageBreak(),p(f'{issue["id"]} / {issue["title"]}','Heading1'),p(f'{issue["discipline"]} · {issue["priority"]} · {issue["status"]}','Heading3'),p(issue['description']),p('Origin: automatic detection and segmentation; human review pending.' if issue.get('automation') and issue['status']=='needs_review' else 'Origin: automatic finding with subsequent review.' if issue.get('automation') else 'Origin: manually reviewed observation.'),Spacer(1,8)])
        for text in [f"Assigned to: {issue['assignee'] or 'Unassigned'} | Due: {issue['dueDate'] or 'Not set'}",f"Location: {e['name']} | {e['level']} | grid {e['grid']}",f"IFC GlobalId: {e['globalId']} | Model v{model['version']}",f"Source: {video['filename']} @ {clock(o['timestamp'])} | Capture date unknown",f"Observation reviewer: {(issue.get('observationReviewer') or 'Human review pending')} | Reviewed: {(issue.get('observationReviewedAt') or 'Not yet reviewed')}"]:flow.append(p(text))
        if o.get('highlight'):
            h=o['highlight']
            flow.extend([Spacer(1,10),PDFImage(BytesIO(evidence_bytes(o,True)),width=480,height=270),p(f"Highlighted: {h['label']} | {h['algorithm']}"),p(f"{highlight_provenance(h)}. The overlay identifies a candidate item; it does not establish a hazard or completion."),Spacer(1,8),PDFImage(BytesIO(cached_snapshot(json.dumps(model,sort_keys=True),e['id'])),width=300,height=195),PageBreak(),p(f"{issue['id']} / Original evidence & review history",'Heading1'),PDFImage(BytesIO(evidence_bytes(o)),width=480,height=270),p(f"Original view, without highlights. {video['filename']} @ {clock(o['timestamp'])}. The unchanged JPEG is included in the BCF package."),p(f"Evidence SHA-256: {h['sourceSha256']}"),p('Highlight history','Heading2')])
            flow.extend(p(f"{event['at']} / {event['by']}: {event['action']} — {event['note']}") for event in o['history'] if event['action'].startswith('highlight'))
        else:
            flow.extend([Spacer(1,10),PDFImage(BytesIO(evidence_bytes(o)),width=480,height=270),p('Source frame. Original clip timestamp retained; illustrative BIM assignment.'),Spacer(1,8),PDFImage(BytesIO(cached_snapshot(json.dumps(model,sort_keys=True),e['id'])),width=380,height=247)])
        flow.extend([p('Issue history','Heading2')]+[p(f"{h['at']} / {h['by']} / {h['action']}: {h['note']} {h.get('resolutionEvidence','')}") for h in issue['history']])
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#657169'));canvas.drawString(40,22,'Fieldlink | Representative model | Clip-relative evidence');canvas.drawRightString(A4[0]-40,22,str(doc.page))
    SimpleDocTemplate(out,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40).build(flow,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()

def make_export(kind,issues,observations,model,videos):
    if kind=='pdf':return make_pdf(issues,observations,model,videos),'fieldlink-punch-list.pdf','application/pdf'
    if kind=='bcf':return make_bcf(issues,observations,model,videos),'fieldlink-issues.bcfzip','application/octet-stream'
    pdf=make_pdf(issues,observations,model,videos);bcf=make_bcf(issues,observations,model,videos);out=BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('fieldlink-punch-list.pdf',pdf);archive.writestr('fieldlink-issues.bcfzip',bcf);archive.write(DATA/'representative.ifc','representative.ifc')
        archive.writestr('manifest.json',json.dumps({'exportedAt':now(),'modelId':model['id'],'modelVersion':model['version'],'bcfVersion':'2.1','validation':'BCF XML schema validation performed at export','receivingApplication':'Not yet independently verified','issues':issues,'observations':observations,'videos':videos},indent=2))
        archive.writestr('READ-ME.txt','FIELDLINK HANDOFF\nLoad representative.ifc, then import fieldlink-issues.bcfzip in a compatible BCF 2.1 tool.\nIndependent receiving-application verification is pending; no universal compatibility claim is made.\nBCF snapshots show the representative model; evidence.png is the separate source frame.\nHighlights (automatic or reviewer-corrected, with explicit provenance) include highlighted.png, source-original.jpg, and highlight.json as additional BCF documents. Masks identify visible items; no automated hazard determination is made.\nFull videos are not included. Clip names/times and SHA-256 hashes are in manifest.json.\nDiscipline maps to Labels, priority to Priority, and workflow status to TopicStatus.\nCapture dates are unknown. Model locations are illustrative.\n')
    return out.getvalue(),'fieldlink-handoff.zip','application/zip'
