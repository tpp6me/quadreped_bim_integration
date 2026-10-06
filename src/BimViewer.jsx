import React, {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {RotateCcw, Maximize2, Layers, MousePointer2} from 'lucide-react';

export default function BimViewer({model,selected,onSelect,observations}){
  const host=useRef(),runtime=useRef(),callback=useRef(onSelect);callback.current=onSelect;
  const [error,setError]=useState(''),[top,setTop]=useState(false),[envelope,setEnvelope]=useState(false);
  useEffect(()=>{
    const el=host.current;let renderer;
    try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});}catch(e){setError('3D rendering is unavailable. Use the element selector below to explore linked evidence.');return;}
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setClearColor('#e9ede4');renderer.outputColorSpace=THREE.SRGBColorSpace;el.appendChild(renderer.domElement);
    renderer.domElement.setAttribute('aria-label','Interactive IFC model. Drag to orbit, scroll to zoom, click an element to select.');renderer.domElement.setAttribute('role','img');
    const scene=new THREE.Scene();scene.add(new THREE.HemisphereLight('#ffffff','#a2ae92',2.3));
    const light=new THREE.DirectionalLight('#fff8e5',3);light.position.set(20,-15,50);scene.add(light);
    const camera=new THREE.OrthographicCamera(-40,40,30,-30,.1,500);camera.up.set(0,0,1);camera.position.set(70,-45,55);
    const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(24,16,1);controls.enableDamping=true;controls.maxPolarAngle=Math.PI*.47;controls.minZoom=.4;controls.maxZoom=6;controls.update();
    const meshes=[];const labels=[];
    const label=(text,x,y,z,color='#52675b',size=2)=>{
      const canvas=document.createElement('canvas');canvas.width=512;canvas.height=96;const ctx=canvas.getContext('2d');ctx.fillStyle=color;ctx.font='500 34px system-ui';ctx.textAlign='center';ctx.fillText(text,256,58);
      const texture=new THREE.CanvasTexture(canvas);const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthTest:false,transparent:true}));sprite.position.set(x,y,z);sprite.scale.set(size*5.3,size,1);scene.add(sprite);labels.push(sprite);
    };
    for(const item of model.elements){
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(item.vertices,3));geometry.setIndex(item.indices);geometry.computeVertexNormals();
      const material=new THREE.MeshStandardMaterial({color:item.color,roughness:.9,metalness:0,side:THREE.DoubleSide});
      const mesh=new THREE.Mesh(geometry,material);mesh.userData=item;mesh.visible=item.category!=='Envelope';scene.add(mesh);meshes.push(mesh);
      if(item.category!=='Space'){
        const edges=new THREE.LineSegments(new THREE.EdgesGeometry(geometry),new THREE.LineBasicMaterial({color:'#52685c',transparent:true,opacity:.3}));mesh.add(edges);
      }
      if(item.category==='Space')label(item.name.split(' · ')[1].toUpperCase(),item.position[0]+item.size[0]/2,item.position[1]+item.size[1]-.8,.5,'#4a6253',2.1);
    }
    const lineMat=new THREE.LineDashedMaterial({color:'#90a38f',dashSize:.3,gapSize:.4,transparent:true,opacity:.7});
    for(const [i,x] of [1,16,32,47].entries()){
      const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,-2,-.01),new THREE.Vector3(x,34,-.01)]);const l=new THREE.Line(g,lineMat);l.computeLineDistances();scene.add(l);label(String.fromCharCode(65+i),x,-3.5,.1,'#677766',2.0);
    }
    for(const [i,y] of [1,11,21,31].entries()){
      const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-2,y,-.01),new THREE.Vector3(50,y,-.01)]);const l=new THREE.Line(g,lineMat);l.computeLineDistances();scene.add(l);label(String(i+1),-3.5,y,.1,'#677766',2.0);
    }
    const markerGroup=new THREE.Group();scene.add(markerGroup);
    for(const o of observations){
      const item=model.elements.find(e=>e.id===o.elementId);if(!item)continue;
      const marker=new THREE.Mesh(new THREE.SphereGeometry(.5,20,12),new THREE.MeshBasicMaterial({color:'#dc9752'}));marker.position.set(item.position[0]+item.size[0]/2,item.position[1]+item.size[1]/2,item.position[2]+item.size[2]+1);marker.userData={...item,observationId:o.id};markerGroup.add(marker);meshes.push(marker);
    }
    let down;
    const onDown=e=>{down=[e.clientX,e.clientY]};
    const onUp=e=>{
      if(!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;
      const rect=renderer.domElement.getBoundingClientRect(),ray=new THREE.Raycaster();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1),camera);
      const hit=ray.intersectObjects(meshes.filter(m=>m.visible),false).find(h=>h.object.userData.id!=='floor');if(hit)callback.current(hit.object.userData.id,hit.object.userData.observationId);
    };
    renderer.domElement.addEventListener('pointerdown',onDown);renderer.domElement.addEventListener('pointerup',onUp);
    const resize=()=>{const w=el.clientWidth,h=el.clientHeight;renderer.setSize(w,h);const aspect=w/h;camera.left=-30*aspect;camera.right=30*aspect;camera.top=30;camera.bottom=-30;camera.updateProjectionMatrix()};
    const observer=new ResizeObserver(resize);observer.observe(el);resize();
    let frame;function animate(){frame=requestAnimationFrame(animate);controls.update();renderer.render(scene,camera)}animate();
    runtime.current={scene,camera,controls,meshes,markerGroup};
    return()=>{cancelAnimationFrame(frame);observer.disconnect();controls.dispose();renderer.domElement.removeEventListener('pointerdown',onDown);renderer.domElement.removeEventListener('pointerup',onUp);scene.traverse(o=>{o.geometry?.dispose();if(o.material){const mats=Array.isArray(o.material)?o.material:[o.material];mats.forEach(m=>{m.map?.dispose();m.dispose()})}});renderer.dispose();renderer.domElement.remove();runtime.current=null};
  },[model]);
  useEffect(()=>{
    const r=runtime.current;if(!r)return;
    for(const marker of [...r.markerGroup.children]){r.markerGroup.remove(marker);marker.geometry.dispose();marker.material.dispose();const index=r.meshes.indexOf(marker);if(index>=0)r.meshes.splice(index,1)}
    for(const o of observations){const item=model.elements.find(e=>e.id===o.elementId);if(!item)continue;const marker=new THREE.Mesh(new THREE.SphereGeometry(.5,20,12),new THREE.MeshBasicMaterial({color:o.automation?'#d78a28':'#dc9752'}));marker.position.set(item.position[0]+item.size[0]/2,item.position[1]+item.size[1]/2,item.position[2]+item.size[2]+1);marker.userData={...item,observationId:o.id};r.markerGroup.add(marker);r.meshes.push(marker)}
  },[model,observations.map(o=>o.id+':'+o.elementId).join('|')]);
  useEffect(()=>{
    runtime.current?.meshes.forEach(mesh=>{if(mesh.material.emissive){mesh.material.color.set(mesh.userData.id===selected?'#e5b663':mesh.userData.color);mesh.material.emissive.set(mesh.userData.id===selected?'#50370c':'#000000');mesh.material.emissiveIntensity=.16;}});
  },[selected,model]);
  useEffect(()=>{runtime.current?.meshes.filter(m=>m.userData.category==='Envelope').forEach(m=>{m.visible=envelope})},[envelope]);
  function reset(plan=false){const r=runtime.current;if(!r)return;r.camera.position.set(...(plan?[24,16,100]:[70,-45,55]));r.controls.target.set(24,16,1);r.camera.zoom=1;r.camera.updateProjectionMatrix();r.controls.update();setTop(plan)}
  return <div className="bim-wrap"><div className="bim-canvas" ref={host}/>{error&&<div className="webgl-error">{error}</div>}<div className="model-top"><span className="light-label"><Layers size={13}/>Representative IFC · v1.0</span><span className="level-label">L00 / Ground Floor</span></div><div className="model-tools"><button title="Reset model view" aria-label="Reset model view" onClick={()=>reset()}><RotateCcw size={16}/></button><button title={top?'Show 3D view':'Show plan view'} aria-label={top?'Show 3D view':'Show plan view'} onClick={()=>reset(!top)}><Maximize2 size={16}/></button><button title="Toggle building envelope" aria-label="Toggle building envelope" aria-pressed={envelope} onClick={()=>setEnvelope(!envelope)}><Layers size={16}/></button></div><div className="model-bottom"><span><MousePointer2 size={12}/>Drag to orbit · select an element</span><span><i className="pin-dot"/>Evidence location</span></div></div>
}
