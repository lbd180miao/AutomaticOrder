const fs=require('fs'),vm=require('vm'),assert=require('assert');
class El {
 constructor(){this.children=[];this.dataset={};this.textContent='';this.value='csrf';this.nodes={};this.attrs={};this.handlers={};}
 querySelector(s){return this.nodes[s] ||= new El();}
 set innerHTML(v){this.children=[new El(),new El(),new El(),new El()];}
 replaceChildren(){this.children=[];}
 appendChild(n){this.children.push(n);}
 addEventListener(name,fn){this.handlers[name]=fn;}
 setAttribute(k,v){this.attrs[k]=v;}
 closest(){return this;}
}
(async()=>{
 const els={}; const get=k=>els[k] ||= new El();let enabled=false,posts=0;
 const document={getElementById:get,querySelector:get,createElement:()=>new El()};
 const context={document,Date,AbortController,URLSearchParams,setTimeout:()=>0,clearTimeout(){},fetch:async(url,opts)=>{
  if(url.includes('plc-listener-debug')) {posts++;enabled=opts.body.get('enabled')==='true';assert.equal(opts.headers['X-CSRFToken'],'csrf');return {ok:true,json:async()=>({enabled})};}
  return {ok:true,json:async()=>url.includes('plc-logs')?{debug:{enabled},running:true,auto_start:true,inputs:{values:{},checked_at:new Date().toISOString()},records:[]}:{devices:['PLC','3D','2D','External'].map(name=>({name,state:'online'}))}};
 }};
 vm.runInNewContext(fs.readFileSync('tmp/debug-listener-ui.js','utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 const button=get('plc-debug-toggle'),grid=get('device-health-grid');
 assert.equal(button.attrs['aria-pressed'],'false');
 await grid.handlers.click({target:button});assert.equal(button.attrs['aria-pressed'],'true');assert(button.textContent.includes('恢复正常'));
 await grid.handlers.click({target:button});assert.equal(button.attrs['aria-pressed'],'false');assert.equal(posts,2);
 assert.equal(get('plc-input-status').children.length,5);
 console.log('PASS UI toggle dark/on/off, five input rows and CSRF');
})().catch(e=>{console.error(e);process.exit(1)});
