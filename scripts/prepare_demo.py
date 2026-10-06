"""Generate a representative IFC and its triangulated browser geometry."""
import json
from pathlib import Path
import uuid
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'
NAMESPACE=uuid.UUID('5b8bb4b3-ecf0-4ecf-9c7f-3db962a31ad7')
def guid(name): return ifcopenshell.guid.compress(uuid.uuid5(NAMESPACE,name).hex)

def build():
    OUT.mkdir(exist_ok=True)
    model=ifcopenshell.file(schema='IFC4')
    def api(operation,**kwargs): return ifcopenshell.api.run(operation,model,**kwargs)
    def entity(kind,name):
        obj=api('root.create_entity',ifc_class=kind,name=name);obj.GlobalId=guid(name);return obj
    project=entity('IfcProject','Fieldlink • Industrial Handover Demonstrator')
    api('unit.assign_unit',units=[api('unit.add_si_unit',unit_type='LENGTHUNIT'),api('unit.add_si_unit',unit_type='AREAUNIT'),api('unit.add_si_unit',unit_type='VOLUMEUNIT')])
    context=api('context.add_context',context_type='Model')
    body=api('context.add_context',context_type='Model',context_identifier='Body',target_view='MODEL_VIEW',parent=context)
    site=entity('IfcSite','Representative site');building=entity('IfcBuilding','Northworks Industrial Facility');storey=entity('IfcBuildingStorey','L00 — Ground Floor');storey.Elevation=0.
    for parent,child in [(project,site),(site,building),(building,storey)]:api('aggregate.assign_object',relating_object=parent,products=[child])
    items=[];entities={}
    def box(key,name,kind,pos,size,color,zone=None,grid='',category='Equipment'):
        obj=entity(kind,name);entities[key]=obj
        x,y,z=map(float,pos);w,d,h=map(float,size)
        vertices=[(x,y,z),(x+w,y,z),(x+w,y+d,z),(x,y+d,z),(x,y,z+h),(x+w,y,z+h),(x+w,y+d,z+h),(x,y+d,z+h)]
        faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        rep=api('geometry.add_mesh_representation',context=body,vertices=[vertices],faces=[faces])
        api('geometry.assign_representation',product=obj,representation=rep)
        if kind=='IfcSpace':api('aggregate.assign_object',relating_object=storey,products=[obj])
        else:api('spatial.assign_container',relating_structure=entities.get(zone,storey),products=[obj])
        pset=api('pset.add_pset',product=obj,name='Fieldlink_Provenance')
        api('pset.edit_pset',pset=pset,properties={'Provenance':'Representative model; manually mapped evidence','Reference':key,'GridReference':grid,'Discipline':'Structural' if category=='Structure' else 'General'})
        items.append({'id':key,'globalId':obj.GlobalId,'name':name,'ifcClass':kind,'position':pos,'size':size,'color':color,'zone':zone,'grid':grid,'category':category,'level':'L00 — Ground Floor'})
        return obj
    box('floor','Ground floor slab','IfcSlab',[0,0,-.35],[48,32,.35],'#c4c5b9',category='Structure')
    zones=[('production','L00-101 · Production Hall',[1,1,.01],[26,17,.04],'#b8c6b0','B2'),('storage','L00-102 · Storage',[29,1,.01],[18,17,.04],'#c6c0a7','D2'),('assembly','L00-103 · Assembly',[1,20,.01],[26,11,.04],'#b7c7be','B3'),('loading','L00-104 · Loading',[29,20,.01],[18,11,.04],'#c3beb6','D3')]
    for key,name,pos,size,color,grid in zones:box(key,name,'IfcSpace',pos,size,color,grid=grid,category='Space')
    for ix,x in enumerate([1,16,32,47]):
        for iy,y in enumerate([1,11,21,31]):box(f'column-{ix}-{iy}',f'Column {chr(65+ix)}{iy+1}','IfcColumn',[x-.2,y-.2,0],[.4,.4,7.5],'#81958d',grid=f'{chr(65+ix)}{iy+1}',category='Structure')
    for i,(x,y) in enumerate([(4,3),(12,3),(20,3),(4,11),(12,11),(20,11)]):
        box(f'machine-{i+1}',f'EQ-{i+1:02} · Process equipment','IfcBuildingElementProxy',[x,y,0],[4.5,3,2.8],'#8eaa9f','production',grid='B2')
    for i,(x,y) in enumerate([(31,3),(38,3),(31,11),(38,11)]):
        box(f'rack-{i+1}',f'ST-{i+1:02} · Storage rack','IfcBuildingElementProxy',[x,y,0],[6,2.2,4.1],'#b99a6d','storage',grid='D2')
    for i,x in enumerate([4,12,20]):box(f'bench-{i+1}',f'AS-{i+1:02} · Assembly station','IfcBuildingElementProxy',[x,24,0],[5,3,1.2],'#8faaa8','assembly',grid='B3')
    box('loading-stage','LD-01 · Staging area','IfcBuildingElementProxy',[34,24,0],[8,4,.8],'#b9ad92','loading',grid='D3')
    box('roof','Roof envelope','IfcRoof',[0,0,7.6],[48,32,.25],'#d1d4cf',category='Envelope')
    box('wall-north','North wall','IfcWall',[0,31.8,0],[48,.2,7.5],'#d1d4cf',category='Envelope')
    box('wall-west','West wall','IfcWall',[0,0,0],[.2,32,7.5],'#d1d4cf',category='Envelope')
    axes=[]
    for axis,positions in [('U',[1.,16.,32.,47.]),('V',[1.,11.,21.,31.])]:
        group=[]
        for i,val in enumerate(positions):
            coords=[(val,-2.,0.),(val,34.,0.)] if axis=='U' else [(-2.,val,0.),(50.,val,0.)]
            curve=model.create_entity('IfcPolyline',Points=[model.create_entity('IfcCartesianPoint',Coordinates=c) for c in coords])
            group.append(model.create_entity('IfcGridAxis',AxisTag=chr(65+i) if axis=='U' else str(i+1),AxisCurve=curve,SameSense=True))
        axes.append(group)
    grid=entity('IfcGrid','Ground floor reference grid');grid.UAxes=axes[0];grid.VAxes=axes[1]
    api('spatial.assign_container',relating_structure=storey,products=[grid])
    model.write(str(OUT/'representative.ifc'))
    settings=ifcopenshell.geom.settings();settings.set(settings.USE_WORLD_COORDS,True)
    for item in items:
        shape=ifcopenshell.geom.create_shape(settings,entities[item['id']])
        item['vertices']=list(shape.geometry.verts);item['indices']=list(shape.geometry.faces)
    output={'id':'northworks-v1','version':'1.0','projectId':project.GlobalId,'name':'Northworks Industrial Facility','provenance':'Representative model','coordinateSystem':'metres; Z up','elements':items}
    (OUT/'model.json').write_text(json.dumps(output))
    print(f'Created IFC4 and extracted {len(items)} element meshes')

if __name__=='__main__':build()
