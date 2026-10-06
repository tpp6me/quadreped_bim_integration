/** Render a narrated, captioned walkthrough on an exact frame/audio timeline.
 * Uses isolated review data and the real application; no live project changes.
 * Run prepare_narration.py first. Requires macOS Chrome, FFmpeg and PyMuPDF.
 */
import {chromium} from 'playwright';
import {spawn,execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {once} from 'node:events';
import {readFile,writeFile,mkdir,mkdtemp,copyFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';


const exec=promisify(execFile),ROOT=process.cwd(),OUT=path.resolve('data/exports/narrated');
await mkdir(OUT,{recursive:true});
const chapters=JSON.parse(await readFile(path.join(OUT,'narration-timing.json'),'utf8'));
const temp=await mkdtemp(path.join(tmpdir(),'fieldlink-narration-'));
const port='8002',base=`http://127.0.0.1:${port}`,fps=12;
const server=spawn(path.resolve('.venv/bin/python'),['-m','server.app'],{env:{...process.env,FIELDLINK_PORT:port,FIELDLINK_DB:path.join(temp,'demo.sqlite')},stdio:['ignore','ignore','pipe']});
let serverLog='';server.stderr.on('data',b=>{serverLog+=b});
let browser;
const timeline=[];
let total=0;
try{
 let ready=false;
 for(let n=0;n<80;n++){try{if((await fetch(base+'/api/health')).ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,200))}
 assert(ready,serverLog);
 browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1,reducedMotion:'reduce'});
 page.setDefaultTimeout(20000);const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base);await page.waitForSelector('.bim-canvas canvas');await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2);
 await page.waitForFunction(async()=>{const p=await(await fetch('/api/project')).json();return p.issues.some(i=>i.automation&&i.id==='FL-001')},null,{timeout:180000});
 const project=await(await fetch(base+'/api/project')).json();
 const automaticIssue=project.issues.find(i=>i.id==='FL-001');
 const automaticObservation=project.observations.find(o=>o.id===automaticIssue.observationId);
 assert.equal(automaticIssue.status,'needs_review');
 assert.equal(automaticIssue.createdBy,'Fieldlink vision');
 assert.equal(automaticObservation.highlight.method,'automatic-sam2');
 assert.equal(automaticObservation.highlight.reviewer,null);
 await writeFile(path.join(OUT,'recording-automation-evidence.json'),JSON.stringify({issue:automaticIssue,observation:automaticObservation},null,2));
 await page.addStyleTag({content:`
   .topbar{visibility:hidden}.app-main main{padding-bottom:135px}
   #film-header{position:fixed;z-index:1001;left:256px;right:32px;top:20px;display:flex;justify-content:space-between;align-items:center;color:#28513d;font:600 16px system-ui;pointer-events:none}
   #film-header small{font-size:11px;font-weight:500;color:#6d8266;letter-spacing:1px}
   #film-captions{position:fixed;z-index:1002;bottom:22px;left:50%;transform:translateX(-50%);width:max-content;max-width:1440px;text-align:center;color:#fff;background:#16372bf2;border:1px solid #b6cb8633;border-radius:12px;padding:17px 27px;font:500 24px/1.45 system-ui;box-shadow:0 4px 30px #13321e22;pointer-events:none}
   #film-card{position:fixed;inset:0;z-index:1000;background:#f3f5ed;display:flex;flex-direction:column;justify-content:center;padding:95px 180px 140px;color:#203d2f;font-family:system-ui}
   #film-card .kicker{font-size:15px;letter-spacing:4px;color:#7d9466;font-weight:600;margin-bottom:30px}
   #film-card h1{font-size:78px;letter-spacing:-4px;line-height:1.1;max-width:1400px;font-weight:600;margin:0 0 27px}
   #film-card p{font-size:27px;line-height:1.6;max-width:1200px;color:#69805d;margin:0}
   #film-card .row{display:flex;gap:22px;margin-top:45px}
   #film-card .tile{padding:25px 29px;border:1px solid #d8e1cc;border-radius:13px;flex:1;background:#fbfcf7;font-size:21px;font-weight:500}
   #film-card .tile small{display:block;font-size:15px;line-height:1.65;color:#879778;margin-top:10px;font-weight:400}
   #film-card .fine{font-size:15px;color:#8b9b7c;margin-top:30px}
   #film-card.report{display:grid;grid-template-columns:1fr 720px;gap:55px;padding:72px 135px 130px;align-items:center}
   #film-card.report h1{font-size:55px;letter-spacing:-2px}#film-card.report p{font-size:23px}
   #film-card.report img{height:840px;max-width:100%;object-fit:contain;box-shadow:0 12px 40px #21452516;border:1px solid #d9e0d1}
   #film-card.pipeline{padding:100px 100px 170px;display:grid;grid-template-columns:1120px 1fr;gap:40px;align-items:center}
   #film-card.pipeline .frame{position:relative;width:1120px;aspect-ratio:16/9;border-radius:12px;overflow:hidden;background:#102a20}
   #film-card.pipeline .frame img,#film-card.pipeline .frame svg{position:absolute;inset:0;width:100%;height:100%;object-fit:fill}
   #film-card.pipeline h1{font-size:44px;letter-spacing:-1px;margin-bottom:20px}
   #film-card.pipeline p{font-size:21px;line-height:1.5}
   #film-card.pipeline .kicker{font-size:12px;letter-spacing:2px;margin-bottom:16px}
   #film-card.pipeline .step{padding:16px 20px;border-left:4px solid #d5decc;margin:15px 0;color:#879778;font-size:20px;background:#fafbf7}
   #film-card.pipeline .step.active{border-color:#55a66d;color:#214c32;background:#e2efdb}
   #film-card.pipeline .step small{display:block;font-size:15px;margin-top:7px;line-height:1.5}
   #film-card.pipeline .fine{font-size:14px;margin-top:22px}
 `});
 await page.evaluate(()=>{const header=document.createElement('div');header.id='film-header';document.body.append(header);const captions=document.createElement('div');captions.id='film-captions';document.body.append(captions)});
 async function card(html,kind=''){
  await page.evaluate(({html,kind})=>{document.getElementById('film-card')?.remove();const card=document.createElement('div');card.id='film-card';card.className=kind;card.innerHTML=html;document.body.append(card)},{html,kind});
 }
 async function removeCard(){await page.evaluate(()=>document.getElementById('film-card')?.remove())}
 async function click(name,exact=true){await page.getByRole('button',{name,exact}).click()}
 async function settle(){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))}
 for(const chapter of chapters){
  let events=[];
  const at=(time,action)=>events.push({frame:Math.floor(time*fps),action});
  if(chapter.id==='intro'){
   await card(`<div class="kicker">FIELDLINK / AUTOMATIC SITE MONITORING</div><h1>Robot footage in.<br>Highlighted issues out.</h1><p>Detect candidate problems, segment the evidence,<br>and create BIM-linked issues automatically.</p><div class="row"><div class="tile">Object detection<small>Grounding DINO locates candidate objects</small></div><div class="tile">Image segmentation<small>SAM 2.1 generates the object masks</small></div><div class="tile">Automatic issues<small>The team reviews findings already created</small></div></div><p class="fine">Real factory footage · Representative BIM · Local inference · Synthetic narration</p>`);
  }
  if(chapter.id==='automatic'){
   await removeCard();await click('Site overview');await page.evaluate(()=>window.scrollTo(0,0));
  }
  if(chapter.id==='detection'){
   await removeCard();
   await click('Issue register');await click('Open FL-001');
   at(chapter.cues[1].start+1,()=>click('Show original'));
   at(chapter.cues[1].start+3,()=>click('Show highlight'));
  }
  if(chapter.id==='pipeline'){
   const h=automaticObservation.highlight,b=h.box;
   await card(`<div><div class="kicker">SOURCE FRAME · ${automaticObservation.videoId} / 01:42</div><div class="frame"><img src="${base}${automaticObservation.evidence}" alt="Original robot video frame"><img id="pipeline-mask" style="visibility:hidden" src="data:image/png;base64,${h.mask}" alt="Automatically generated segmentation mask"><svg id="pipeline-box" style="visibility:hidden" viewBox="0 0 1000 562.5"><rect x="${b.x*1000}" y="${b.y*562.5}" width="${b.width*1000}" height="${b.height*562.5}" fill="none" stroke="#ffc741" stroke-width="3"/></svg></div><p class="fine">Actual saved model outputs, revealed in sequence · Original image preserved</p></div><div><div class="kicker">SYSTEM ACTIONS / BEFORE REVIEW</div><h1>Evidence ready.<br>Issue created.</h1><div id="pipeline-detect" class="step">1 / Detect the object<small>Grounding DINO · Score ${h.detectionScore.toFixed(2)}</small></div><div id="pipeline-segment" class="step">2 / Highlight the cable<small>SAM 2.1 · Generated segmentation mask</small></div><div id="pipeline-create" class="step">3 / Create the issue<small id="pipeline-issue-detail">Awaiting this step in the sequence</small></div><p class="fine">Screening check: possible floor cable.<br>Detection score is not hazard probability.</p></div>`,'pipeline');
   await page.waitForFunction(()=>[...document.querySelectorAll('#film-card img')].every(i=>i.complete&&i.naturalWidth>0));
   at(chapter.cues[1].start,()=>page.evaluate(()=>{document.getElementById('pipeline-box').style.visibility='visible';document.getElementById('pipeline-detect').classList.add('active')}));
   at(chapter.cues[2].start,()=>page.evaluate(()=>{document.getElementById('pipeline-mask').style.visibility='visible';document.getElementById('pipeline-segment').classList.add('active')}));
   at(chapter.cues[3].start,()=>page.evaluate(()=>{document.getElementById('pipeline-create').classList.add('active');document.getElementById('pipeline-issue-detail').textContent='FL-001 · Needs review · Created by Fieldlink vision'}));
   at(chapter.cues[3].start+2,()=>page.screenshot({path:path.join(OUT,'pipeline-created-preview.png')}));
  }
  if(chapter.id==='context'){
   await click('Open source evidence');await page.locator('.workspace-grid').scrollIntoViewIfNeeded();
   at(3,()=>click('Show plan view'));at(7,()=>click('Reset model view'));
  }
  if(chapter.id==='review'){
   await click('Issue register');await click('Open FL-001');
   at(4,async()=>{await page.getByRole('combobox',{name:/^Status/}).selectOption('open');await page.getByLabel('Update / verification note').fill('Demo review: visible cable confirmed. Check route use and cable protection with the site team.');});
   at(chapter.duration-2,async()=>{await click('Confirm issue');await page.waitForSelector('.modal',{state:'hidden'})});
  }
  if(chapter.id==='assign'){
   await click('Open FL-001');
   at(2,async()=>{await page.getByRole('combobox',{name:/^Status/}).selectOption('assigned');await page.getByLabel('Responsible party').fill('Demo site team');await page.getByLabel('Due date').fill('2026-10-20');await page.getByLabel('Update / verification note').fill('Demo assignment: check the route and provide follow-up evidence.');});
   at(chapter.cues[1].start+1,async()=>{await click('Save issue update');await page.waitForSelector('.modal',{state:'hidden'});await page.evaluate(()=>window.scrollTo(0,0))});
  }
  if(chapter.id==='export'){
   await click('Reports & handoff');await page.evaluate(()=>window.scrollTo(0,0));
   at(3.5,async()=>{const download=page.waitForEvent('download',{timeout:120000});await click('Download ZIP');await (await download).saveAs(path.join(OUT,'narrated-demo-handoff.zip'));});
  }
  if(chapter.id==='report'){
   await exec('python3',['-c',`import zipfile,fitz
from pathlib import Path
p=Path(${JSON.stringify(OUT)})
with zipfile.ZipFile(p/'narrated-demo-handoff.zip') as z: data=z.read('fieldlink-punch-list.pdf')
(p/'narrated-demo-punch-list.pdf').write_bytes(data)
doc=fitz.open(stream=data,filetype='pdf')
page=next(page for page in doc if 'FL-001 /' in page.get_text() and 'Highlighted:' in page.get_text())
page.get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(str(p/'report-page.png'))`]);
   const image=(await readFile(path.join(OUT,'report-page.png'))).toString('base64');
   await card(`<div><div class="kicker">THE ACTUAL EXPORTED REPORT</div><h1>Every issue has<br>its evidence attached.</h1><p>An automatically detected object.<br>A generated segmentation mask.<br>Source evidence, model context, and review history.</p><div class="row"><div class="tile">FL-001 / Assigned<small>Detected and created automatically<br>Reviewed and assigned by the demo site team</small></div></div><p class="fine">Original image preserved separately. Detection scores are not hazard probabilities.</p></div><img src="data:image/png;base64,${image}" alt="Exported PDF issue page">`,'report');
   await page.waitForFunction(()=>document.querySelector('#film-card img')?.complete);
  }
  if(chapter.id==='outro'){
   await card(`<div class="kicker">NEXT / A CONSTRUCTION PILOT</div><h1>Automate the finding.<br>Keep people accountable.</h1><p>Validate each check on project footage,<br>then connect it to real BIM and schedule data.</p><div class="row"><div class="tile">Broader site checks<small>Validated object classes and site-specific rules</small></div><div class="tile">Actual BIM + schedule<small>Registered locations and planned work packages</small></div><div class="tile">Repeat captures<small>Verified progress and follow-up evidence</small></div></div><p class="fine">Current demo screens for candidate floor cables. Construction progress measurement and independent BIM-tool import remain pending.</p>`);
  }
  events.sort((a,b)=>a.frame-b.frame);
  const frames=Math.ceil(chapter.duration*fps),duration=frames/fps,output=path.join(OUT,`${chapter.id}.mp4`);
  const encoder=spawn('ffmpeg',['-v','error','-f','image2pipe','-framerate',String(fps),'-vcodec','mjpeg','-i','pipe:0','-i',chapter.audio,'-map','0:v','-map','1:a','-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-af','apad','-t',String(duration),'-movflags','+faststart','-y',output],{stdio:['pipe','ignore','pipe']});
  const done=new Promise((resolve,reject)=>{let log='';encoder.stderr.on('data',b=>log+=b);encoder.on('error',reject);encoder.on('close',code=>code===0?resolve():reject(Error(log)))});
  for(let frame=0;frame<frames;frame++){
   const t=frame/fps;
   while(events.length&&events[0].frame<=frame){await events.shift().action();await settle()}
   if(chapter.id==='context'&&frame%2===0&&t<2.5){
    await page.locator('video').evaluate(async(v,time)=>{v.muted=true;v.pause();if(Math.abs(v.currentTime-time)<.02)return;await new Promise(resolve=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=time})},102+t);
   }
   const cue=chapter.cues.find(c=>t>=c.start&&t<c.end);
   await page.evaluate(({title,caption})=>{document.getElementById('film-header').innerHTML='<span>'+title+'</span><small>PRERECORDED · LOCAL MODEL RESULTS MAY BE CACHED · SYNTHETIC VOICE</small>';const element=document.getElementById('film-captions');element.textContent=caption;element.style.display=caption?'block':'none'},{title:chapter.title,caption:cue?.text||''});
   const screenshot=await page.screenshot({type:'jpeg',quality:85,animations:'disabled'});
   if(!encoder.stdin.write(screenshot))await once(encoder.stdin,'drain');
   if(frame===Math.floor(frames/2))await page.screenshot({path:path.join(OUT,`${chapter.id}-preview.png`)});
  }
  encoder.stdin.end();await done;
  timeline.push({...chapter,start:total,end:total+duration,renderedDuration:duration});total+=duration;
  console.log(`Rendered ${chapter.id}: ${duration.toFixed(2)}s (${frames} frames)`,true);
 }
 assert.deepEqual(errors,[]);
 await writeFile(path.join(OUT,'chapters.concat'),chapters.map(c=>`file '${c.id}.mp4'`).join('\n')+'\n');
 await exec('ffmpeg',['-v','error','-f','concat','-safe','0','-i',path.join(OUT,'chapters.concat'),'-c','copy','-movflags','+faststart','-metadata','title=Fieldlink — Robot evidence and BIM','-metadata','comment=Prerecorded local demonstration. Synthetic narration: macOS Samantha. Representative BIM locations.','-y',path.join(OUT,'fieldlink-narrated-demo.mp4')]);
 function stamp(time){const ms=Math.round(time*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')},${String(ms%1000).padStart(3,'0')}`}
 let index=1;const subtitles=timeline.flatMap(c=>c.cues.map(cue=>`${index++}\n${stamp(c.start+cue.start)} --> ${stamp(c.start+cue.end)}\n${cue.text}\n`)).join('\n');
 await writeFile(path.join(OUT,'fieldlink-narrated-demo.srt'),subtitles);
 await copyFile(path.join(OUT,'fieldlink-narrated-demo.mp4'),path.join(OUT,'fieldlink-automatic-workflow-demo.mp4'));
 await copyFile(path.join(OUT,'fieldlink-narrated-demo.srt'),path.join(OUT,'fieldlink-automatic-workflow-demo.srt'));
 await writeFile(path.join(OUT,'timeline.json'),JSON.stringify({fps,duration:total,voice:'Samantha',syntheticNarration:true,chapters:timeline},null,2));
 await writeFile(path.join(OUT,'transcript.txt'),chapters.map(c=>`${c.title}\n${c.sentences.join(' ')}\n`).join('\n'));
 console.log(`DONE: ${total.toFixed(2)}s narrated demo with exact sentence captions.`);
}catch(error){console.error(serverLog.slice(-5000));throw error}finally{await browser?.close();server.kill('SIGTERM')}
