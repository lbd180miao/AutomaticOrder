const fs=require('fs'),vm=require('vm'),assert=require('assert');
class El {
 constructor(){this.children=[];this.dataset={};this.textContent='';this.value='';this.nodes={};}
 querySelector(s){return this.nodes[s] ||= new El();}
 set innerHTML(v){this.children=[new El(),new El(),new El()];}
 replaceChildren(){this.children=[];}
 appendChild(n){this.children.push(n);}
 addEventListener(){}
}
async function check(values,error='',running=true){
 const els={}; const get=k=>els[k] ||= new El();
 const document={getElementById:get,querySelector:get,createElement:()=>new El()};
 const context={document,Date,AbortController,encodeURIComponent,setTimeout:()=>0,clearTimeout(){},fetch:async url=>({ok:true,json:async()=>url.includes('plc-logs')?{running,auto_start:true,inputs:{values,error,checked_at:new Date().toISOString()},records:[]}:{devices:['PLC','3D','2D'].map(name=>({name,state:'online'}))}})};
 vm.runInNewContext(fs.readFileSync('tmp/four-input-ui.js','utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 const rows=get('plc-input-status').children.map(e=>e.textContent);
 assert.equal(rows.length,4);
 ['DB2.DBB24','DB2.DBX46.2','DB2.DBX46.3','DB2.DBX46.4'].forEach((v,i)=>assert(rows[i].includes(v)));
 return rows;
}
(async()=>{
 assert((await check({})).every(v=>v.endsWith('正在监听')));
 const high=await check({rack_barcode:'<script>RACK</script>',position_trigger:true,foam_trigger:true,boxing_trigger:true});
 assert(high.every(v=>v.includes('已读到信号')));
 assert((await check({},'offline')).every(v=>v.includes('正在重连')));
 assert((await check({},'',false)).every(v=>v.includes('正在启动自动监听')));
 console.log('PASS: four addresses, waiting, signal text, disconnected and stopped states');
})();
