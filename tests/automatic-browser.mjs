import {chromium} from 'playwright';
import {spawn} from 'node:child_process';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';

const temp=await mkdtemp(path.join(tmpdir(),'fieldlink-auto-browser-'));
const out=path.resolve('data/exports/automatic');await mkdir(out,{recursive:true});
const base='http://127.0.0.1:8003';
const server=spawn(path.resolve('.venv/bin/python'),['-m','server.app'],{env:{...process.env,FIELDLINK_PORT:'8003',FIELDLINK_DB:path.join(temp,'demo.sqlite'),FIELDLINK_AUTORUN:'1'},stdio:['ignore','ignore','pipe']});
let log='';server.stderr.on('data',b=>log+=b);let browser;
try{
 for(let n=0;n<80;n++){try{if((await fetch(base+'/api/health')).ok)break}catch{}await new Promise(r=>setTimeout(r,200))}
 browser=await chromium.launch({channel:'chrome',headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(25000);
 await page.goto(base);await page.getByRole('heading',{name:'The system finds it. Your team decides the action.'}).waitFor();
 await page.waitForFunction(async()=>{const p=await(await fetch('/api/project')).json();return p.issues.some(i=>i.id==='FL-001'&&i.automation)},null,{timeout:180000});
 let p=await(await fetch(base+'/api/project')).json();let issue=p.issues.find(i=>i.id==='FL-001');assert.equal(issue.status,'needs_review');assert.equal(issue.createdBy,'Fieldlink vision');assert.equal(issue.observationReviewer,null);
 const observation=p.observations.find(o=>o.id===issue.observationId);assert.equal(observation.highlight.method,'automatic-sam2');assert(observation.highlight.mask);assert.equal(observation.highlight.reviewer,null);
 console.log('Real detection automatically created a highlighted issue before any UI action.');
 await page.reload();await page.getByRole('button',{name:'Issue register',exact:true}).click();await page.getByRole('button',{name:'Open FL-001',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.locator('.segmentation-mask').waitFor();await page.screenshot({path:path.join(out,'automatic-issue.png')});
 await dialog.getByRole('button',{name:'Show original',exact:true}).click();assert.equal(await dialog.locator('.segmentation-mask').count(),0);await dialog.getByRole('button',{name:'Show highlight',exact:true}).click();
 await page.getByRole('combobox',{name:/^Status/}).selectOption('open');await page.getByLabel('Update / verification note').fill('Test review: candidate cable visible; assess route use.');await page.getByRole('button',{name:'Confirm issue',exact:true}).click();await page.waitForSelector('.modal',{state:'hidden'});
 p=await(await fetch(base+'/api/project')).json();assert.equal(p.issues.find(i=>i.id==='FL-001').status,'open');
 // A dismissal is a separate review action; it does not delete the source or mask.
 const second=p.issues.find(i=>i.id!=='FL-001'&&i.status==='needs_review');
 if(second){await page.getByRole('button',{name:`Open ${second.id}`,exact:true}).click();await page.getByRole('combobox',{name:/^Status/}).selectOption('dismissed');await page.getByLabel('Update / verification note').fill('Test dismissal to exercise false-positive triage.');await page.getByRole('button',{name:'Dismiss issue',exact:true}).click();await page.waitForSelector('.modal',{state:'hidden'});}
 for(const width of [1440,768,390,320]){await page.setViewportSize({width,height:1000});await page.getByRole('button',{name:'Site overview',exact:true}).click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`Automatic dashboard overflows at ${width}`);}
 await page.setViewportSize({width:1440,height:1100});await page.screenshot({path:path.join(out,'automatic-dashboard.png'),fullPage:true});
 await page.getByRole('button',{name:'Reports & handoff',exact:true}).click();const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'Download ZIP',exact:true}).click();await(await downloaded).saveAs(path.join(out,'automatic-handoff.zip'));
 assert.deepEqual(errors,[]);await writeFile(path.join(out,'browser-checks.json'),JSON.stringify({passed:true,realModels:true,automaticCreationBeforeReview:true,automaticMaskBeforeReview:true,originalToggle:true,confirmation:true,dismissal:!!second,responsiveWidths:[1440,768,390,320],export:true,errors},null,2));console.log('PASS: automatic creation, generated mask, comparison, review, responsive dashboard, export.');
}catch(e){console.error(log.slice(-2000));throw e}finally{await browser?.close();server.kill('SIGTERM')}
