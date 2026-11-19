const assert=require('node:assert/strict');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const path=require('node:path');
process.chdir(path.resolve(__dirname,'..'));
// Render current templates without starting a server or touching hardware.
const html=execFileSync(process.env.PYTHON || '.venv/Scripts/python.exe',['-c',
 "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','AutomaticOrder.settings'); import django; django.setup(); from django.template.loader import render_to_string; import sys; sys.stdout.buffer.write(render_to_string('vision/foam_stream_workbench.html', {'csrf_token':'test'}).encode('utf-8'))"]);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'D:/Scripts/FrciblyK12/.venv/Lib/site-packages/playwright/driver/package');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  let manual=false,stale=false;const actions=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const state=()=>({success:true,running:true,manual,stale,preview_stale:stale,generation:1,processing_fps:12,error:'',image:stale?null:'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7',result:stale?null:{state:'NORMAL',sides:{left:{state:'NORMAL'},right:{state:'NORMAL'}},registration:{status:'REGISTERED',view:'near'},elapsed_ms:20,first_ng:{}}});
  await page.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.pathname==='/vision/foam-inspector/')return route.fulfill({contentType:'text/html',body:html});
   if(u.pathname.endsWith('/config/'))return route.fulfill({json:{success:true,ready:true,profile_name:'test',samples:[]}});
   if(u.pathname.endsWith('/live/control/')){const a=route.request().postDataJSON().action;actions.push(a);manual=a==='enter_manual';return route.fulfill({json:state()});}
   if(u.pathname.endsWith('/live/'))return route.fulfill({json:state()});
   if(u.pathname.startsWith('/static/')){const p=u.pathname.slice(1);if(fs.existsSync(p))return route.fulfill({path:p});}
   return route.fulfill({body:''});
  });
  await page.goto('http://foam.test/vision/foam-inspector/');
  await page.locator('#fs-live-tab').click();
  await page.waitForFunction(()=>document.getElementById('fs-mode-label').textContent.includes('自动监控'));
  assert.equal(await page.locator('#fs-empty-title').textContent(),'等待相机实时画面');
  await page.locator('#fs-start-live').click();
  await page.waitForFunction(()=>document.getElementById('fs-mode-label').textContent.includes('自动工序已暂停'));
  await page.locator('#fs-stop-live').click();
  await page.waitForFunction(()=>document.getElementById('fs-mode-label').textContent.includes('自动监控'));
  assert.deepEqual(actions,['enter_manual','resume_auto']);
  stale=true;
  await page.waitForFunction(()=>document.getElementById('fs-left').textContent==='未确认');
  assert.equal(await page.locator('#fs-image').isVisible(),false);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:'tmp/foam-live-review.png',fullPage:true});
  console.log('PASS: manual/resume controls, camera placeholder, stale result and preview clearing; no browser errors');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
