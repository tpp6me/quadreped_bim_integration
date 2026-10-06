import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdtemp,mkdir,writeFile,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';
import {drawBox,drawStroke} from '../scripts/highlight-browser-helpers.mjs';

// Isolated SQLite state: browser verification never changes the presenter's live project.
const temp=await mkdtemp(path.join(tmpdir(),'fieldlink-browser-'));
const artifacts=path.resolve('data/exports/verification');await mkdir(artifacts,{recursive:true});
const recordMode=process.argv.includes('--record');
const port=process.env.FIELDLINK_TEST_PORT||'8001';const base=`http://127.0.0.1:${port}`;
const server=spawn(path.resolve('.venv/bin/python'),['-m','server.app'],{env:{...process.env,FIELDLINK_AUTORUN:'0',FIELDLINK_PORT:port,FIELDLINK_DB:path.join(temp,'demo.sqlite')},stdio:['ignore','ignore','pipe']});
let serverErrors='';server.stderr.on('data',chunk=>{serverErrors+=chunk});
let browser,context;
try{
 let ready=false;
 for(let i=0;i<60;i++){try{const r=await fetch(base+'/api/health');if(r.ok){ready=true;break}}catch{}await new Promise(r=>setTimeout(r,250))}
 assert(ready,`Test API did not start: ${serverErrors}`);
 browser=await chromium.launch({headless:true,slowMo:recordMode?200:0,channel:process.env.FIELDLINK_BROWSER_CHANNEL||'chrome'});
 context=await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce',recordVideo:{dir:artifacts,size:{width:1440,height:1100}}});
 let page=await context.newPage();page.setDefaultTimeout(20000);console.log('Browser ready');const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{document.addEventListener('DOMContentLoaded',()=>{const label=document.createElement('div');label.id='recording-label';label.textContent='PRERECORDED DEMO · SAMPLE REVIEWER · INDEPENDENT BIM IMPORT PENDING';label.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#18392e;color:#daedb4;text-align:center;font:11px system-ui;padding:7px;z-index:9999;pointer-events:none';document.body.append(label)})});
 async function step(text){await page.evaluate(text=>{const label=document.getElementById('recording-label');if(label)label.textContent='PRERECORDED DEMO · '+text},text);if(recordMode)await new Promise(resolve=>setTimeout(resolve,4500));}
 await page.goto(base);await page.waitForSelector('.bim-canvas canvas');await page.waitForFunction(()=>document.querySelector('video')?.readyState>=2);
 assert(Math.abs(await page.locator('video').evaluate(v=>v.currentTime)-102)<1);
 await page.screenshot({path:path.join(artifacts,'workspace.png'),fullPage:true});console.log('Model and initial video loaded');await step('1. Real factory footage linked to a representative IFC model');
 await page.locator('video').evaluate(v=>{v.muted=true;v.play().catch(()=>{})});await page.waitForFunction(()=>document.querySelector('video').currentTime>103,null,{timeout:20000});await page.locator('video').evaluate(v=>v.pause());console.log('Video playback passed');
 await page.getByRole('button',{name:'Evidence library',exact:true}).click();
 await page.getByRole('textbox',{name:'Search evidence'}).fill('cables on floor');await page.waitForFunction(()=>document.querySelectorAll('.evidence-card').length===1);
 await step('2. Search curated descriptions and jump to the source timestamp');await page.locator('.evidence-card').click();await page.waitForSelector('.bim-canvas canvas');
 await page.getByRole('button',{name:'Review observation',exact:true}).click();
 await page.getByLabel('Reviewer',{exact:true}).fill('Demo reviewer');
 await page.getByLabel('Review note').fill('Presentation example: visible cable confirmed; site access requirements still need checking.');
 await step('3. A reviewer checks the evidence and records the decision');await page.getByRole('button',{name:'Save review',exact:true}).click();await page.waitForSelector('.modal',{state:'hidden'});
 console.log('Review saved');await page.getByRole('button',{name:'Create issue',exact:true}).click();
 await page.getByRole('dialog').getByRole('button',{name:'Create issue',exact:true}).click();await page.waitForSelector('.modal',{state:'hidden'});
 await page.getByRole('button',{name:'Issue register'}).click();await page.getByRole('button',{name:'Open FL-001',exact:true}).click();
 await page.getByRole('combobox',{name:/^Status/}).selectOption('assigned');await page.getByLabel('Responsible party').fill('Demo site team');await page.getByLabel('Due date').fill('2026-10-20');await page.getByLabel('Update / verification note').fill('Demo assignment: review access and cable protection on the next walkdown.');
 await step('4. Assign responsibility and a due date — sample demo assignment');await page.getByRole('button',{name:'Save issue update'}).click();await page.waitForSelector('.modal',{state:'hidden'});
 await page.reload();await page.waitForSelector('.bim-canvas canvas');await page.getByRole('button',{name:'Issue register'}).click();assert((await page.locator('tbody').innerText()).includes('Demo site team'));
 console.log('Issue assignment persisted');
 await page.getByRole('button',{name:'Open FL-001',exact:true}).click();
 await page.getByLabel('Responsible party').fill('Draft owner retained');
 await page.getByRole('button',{name:'Highlight item',exact:true}).click();
 const selection=JSON.parse(await readFile('scripts/demo-highlight-selection.json','utf8'));
 await page.getByLabel('Item label').fill(selection.label);
 await drawBox(page,selection.box);
 for(const stroke of selection.strokes)await drawStroke(page,stroke);
 await page.getByRole('button',{name:'Segment selection',exact:true}).click();
 await page.locator('.segmentation-mask').waitFor();
 await page.getByRole('button',{name:'Show original',exact:true}).click();assert.equal(await page.locator('.segmentation-mask').count(),0);
 await page.getByRole('button',{name:'Show highlight',exact:true}).click();
 await page.screenshot({path:path.join(artifacts,'highlight-editor.png')});
 for(const width of [390,320]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Highlight editor overflow at ${width}`)}
 await page.setViewportSize({width:1440,height:1100});
 await page.getByRole('button',{name:'Confirm highlight',exact:true}).click();
 await page.getByLabel('Responsible party').waitFor();assert.equal(await page.getByLabel('Responsible party').inputValue(),'Draft owner retained');
 await page.getByRole('button',{name:'Close dialog',exact:true}).click();
 await page.reload();await page.waitForSelector('.bim-canvas canvas');await page.getByRole('button',{name:'Issue register',exact:true}).click();await page.getByRole('button',{name:'Open FL-001',exact:true}).click();
 await page.locator('.segmentation-mask').waitFor();assert.equal(await page.getByLabel('Responsible party').inputValue(),'Demo site team');
 await page.screenshot({path:path.join(artifacts,'highlighted-issue.png')});
 await page.getByRole('button',{name:'Close dialog',exact:true}).click();
 console.log('Segmentation, original toggle, confirmation, draft preservation and reload passed');
 await page.getByRole('button',{name:'Reports & handoff'}).click();
 await step('5. Export PDF, BCF, IFC and a traceable evidence manifest');const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'Download ZIP',exact:true}).click();const download=await downloadPromise;await download.saveAs(path.join(artifacts,'sample-handoff.zip'));
 await page.screenshot({path:path.join(artifacts,'reports.png'),fullPage:true});console.log('Handoff downloaded');await step('6. BCF XML validated; independent BIM-tool import remains pending');const recording=page.video();await context.close();await recording.saveAs(path.join(artifacts,'fallback-walkthrough.webm'));context=await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce'});page=await context.newPage();page.setDefaultTimeout(20000);page.on('pageerror',e=>errors.push(e.message));await page.goto(base);await page.waitForSelector('.bim-canvas canvas');
 await page.getByRole('button',{name:'Evidence library',exact:true}).click();await page.getByRole('textbox',{name:'Search evidence'}).fill('cracked concrete beam');await page.getByRole('heading',{name:'No matching evidence'}).waitFor();
 await page.getByRole('textbox',{name:'Search evidence'}).fill('');await page.waitForFunction(()=>document.querySelectorAll('.evidence-card').length===6);
 // Every original file can load and seek. Exercise one frame without downloading each whole file.
 for(let i=1;i<=10;i++){
   const id=`v${String(i).padStart(2,'0')}`;
   const check=await page.evaluate(async({id})=>{const video=document.createElement('video');video.muted=true;video.preload='metadata';video.src='/media/'+id;document.body.append(video);try{return await new Promise(resolve=>{const timer=setTimeout(()=>resolve(false),15000);video.onerror=()=>{clearTimeout(timer);resolve(false)};video.onloadedmetadata=()=>{video.currentTime=30};video.onseeked=()=>{clearTimeout(timer);resolve(video.currentTime===30)}})}finally{video.pause();video.removeAttribute('src');video.load();video.remove()}},{id});assert(check,`Video ${id} did not load/seek`);
 }
 for(const width of [1440,1024,768,390,320]){
   await page.setViewportSize({width,height:1000});
   for(const view of ['Site overview','Evidence library','Issue register','Reports & handoff']){
    await page.getByRole('button',{name:view,exact:view!=='Issue register'}).click();
    const overflow=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,items:[...document.querySelectorAll('body *')].filter(el=>el.getBoundingClientRect().right>innerWidth+1).map(el=>({tag:el.tagName,class:el.className,right:el.getBoundingClientRect().right})).slice(0,12)}));assert.equal(overflow.overflow,false,`Overflow: ${view} at ${width} ${JSON.stringify(overflow.items)}`);
   }
 }
 await page.setViewportSize({width:390,height:844});await page.getByRole('button',{name:'Site overview',exact:true}).click();await page.screenshot({path:path.join(artifacts,'mobile.png')});
 assert.deepEqual(errors,[]);
 await writeFile(path.join(artifacts,'checks.json'),JSON.stringify({passed:true,checks:['Model render and video seeking','Curated search and no-result state','Review, issue creation, assignment and persistence','Reviewer-guided segmentation, comparison, persistence and retained issue drafts','Highlight editor at mobile widths','PDF/BCF/IFC bundle download','All ten source videos load and seek','Four app views at five widths','No browser JavaScript errors'],independentBimImport:'pending'},null,2));
 console.log('PASS: browser review-to-handoff flow, video playback, ten source clips, persistence, downloads, responsive layouts.');
 await context.close();context=null;
}catch(error){if(context){await context.pages()[0]?.screenshot({path:path.join(artifacts,'failure.png'),fullPage:true});}throw error;}finally{if(context)await context.close();if(browser)await browser.close();server.kill('SIGTERM')}
