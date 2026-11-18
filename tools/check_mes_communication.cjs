const fs=require('fs'),vm=require('vm'),assert=require('assert');
class El {
 constructor(){this.children=[];this.dataset={};this.value='';this.style={};this.handlers={};this.nodes={};this.elements={namedItem:n=>this.nodes[n] ||= new El()};}
 append(...nodes){this.children.push(...nodes)}
 replaceChildren(...nodes){this.children=nodes}
 querySelector(s){return this.nodes[s] ||= new El()}
 addEventListener(n,f){this.handlers[n]=f}
 showModal(){this.open=true} close(){this.open=false;this.handlers.close?.()}
}
(async()=>{
 const els={},get=id=>els[id] ||= new El();
 get('mes-communication').dataset={statusUrl:'/status',controlUrl:'/control',detailUrl:'/detail/00000000-0000-0000-0000-000000000000'};
 const classes=new Set();
 const events=[{kind:'queued',created:1},{kind:'mes_request',created:2,data:{payload:'REQUEST_NOISE'}},{kind:'mes_response',created:3,data:{result:'REPEATED_RESULT'}},{kind:'gateway_response',created:4,data:{state:'running'}},{kind:'gateway_response',created:5,data:{state:'succeeded'}}];
 const task={id:'task1',action:'UPLOAD_BOXING_RESULT',state:'accepted',created:1,payload:{rack_code:'RACK001'},result:{}};
 let online=true,posts=[];
 const context={document:{documentElement:{classList:{add:n=>classes.add(n),remove:n=>classes.delete(n)}},getElementById:get,createElement:()=>new El()},Date,Map,Set,Uint8Array,URLSearchParams,window:{location:{search:''}},crypto:require('crypto').webcrypto,setInterval(){},fetch:async(url,opts)=>{
  if(url==='/detail/task1')return {ok:true,json:async()=>({success:true,task,events})};
  if(url==='/control'){posts.push(JSON.parse(opts.body));return {ok:true,json:async()=>({success:true,id:'task1'})};}
  return {ok:true,json:async()=>({connected:online,tasks:[task],outbox:[],events:[]})};
 }};
 vm.runInNewContext(fs.readFileSync('static/mes/communication.js','utf8'),context);
 await new Promise(resolve=>setImmediate(resolve));
 const form=get('comm-send'); form.elements.namedItem('action').value='UPLOAD_BOXING_RESULT';form.elements.namedItem('rack_code').value='RACK001';
 await form.handlers.submit({preventDefault(){}});
 assert.equal(posts[0].operation,'send');assert.equal(posts[0].rack_code,'RACK001');
 assert.equal(get('comm-result-status').textContent,'等待外部电脑查询');
 task.state='succeeded';task.result={success:true,bin_code:'BIN001'};
 await get('comm-refresh').handlers.click();
 assert.equal(get('comm-result-status').textContent,'成功');assert(get('comm-response-json').textContent.includes('BIN001'));
 await get('comm-records').children[0].children[4].children[0].handlers.click();assert(get('comm-record-dialog').open);
 assert(classes.has('comm-detail-open'));
 const detailText=get('comm-record-detail').children.map(e=>e.textContent).join('\n');
 assert(detailText.includes('BIN001'));assert(detailText.includes('开始查询 MES'));assert(detailText.includes('收到 MES 返回信息'));
 assert(!detailText.includes('REQUEST_NOISE'));assert(!detailText.includes('REPEATED_RESULT'));assert(!detailText.includes('请求编号'));
 assert.equal((detailText.match(/AGV 收到返回结果/g)||[]).length,1);
 get('comm-close-record').handlers.click();assert(!get('comm-record-dialog').open);
 assert(!classes.has('comm-detail-open'));
 online=false;await get('comm-refresh').handlers.click();assert(get('comm-connection').textContent.includes('离线'));assert(get('comm-response-json').textContent.includes('BIN001'));
 assert.equal(posts.length,1);
 console.log('PASS: send once, automatic wait/result, record details, offline retains received result');
})().catch(e=>{console.error(e);process.exit(1)});
