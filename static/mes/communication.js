(() => {
 'use strict';
 const root=document.getElementById('mes-communication'); if(!root)return;
 const $=id=>document.getElementById(id), form=$('comm-send'), field=name=>form.elements.namedItem(name);
 const names={GET_RACK_RECIPE:'查询料框类型',UPLOAD_PRODUCT_BARCODE:'产品绑定',UPLOAD_BOXING_RESULT:'装箱完成 / 获取区位号'};
 const states={pending:'等待发送',accepted:'等待外部电脑查询',running:'外部电脑查询中',waiting_manual:'等待外部电脑处理',succeeded:'成功',failed:'失败',unknown:'结果待核对'};
 const terminal=new Set(['succeeded','failed','unknown']);
 let data={tasks:[],outbox:[],events:[]}, tasks=[], selected='', loading=false, sending=false, requestId=null, lastBody='';
 const node=(tag,text)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e;};
 const uuid=()=> '10000000-1000-4000-8000-100000000000'.replace(/[018]/g,c=>(Number(c)^crypto.getRandomValues(new Uint8Array(1))[0]&15>>Number(c)/4).toString(16));
 const date=value=>value?new Date(value*1000).toLocaleString('zh-CN'):'—';
 function merge(){
  const map=new Map((data.tasks||[]).map(t=>[t.id,{...t}]));
  for(const local of data.outbox||[]) {
   const remote=map.get(local.id);
   // Local production results are authoritative once persisted by this computer.
   map.set(local.id,{...remote,...local,remote_state:remote?.state});
  }
  tasks=[...map.values()].sort((a,b)=>b.created-a.created);
 }
 function result(){
  const task=tasks.find(t=>t.id===selected); if(!task)return;
  $('comm-result-status').textContent=states[task.state]||task.state;
  $('comm-result-status').dataset.state=task.state;
  const values=[['接口',names[task.action]||task.action],['料框码',task.payload.rack_code],['产品条码',task.payload.product_code],['料框类型',task.result?.pkg_type_code],['区位号',task.result?.bin_code],['请求编号',task.id]];
  $('comm-result-fields').replaceChildren();
  for(const [label,value] of values)if(value!==undefined&&value!==null&&value!=='') {const row=node('div');row.append(node('dt',label),node('dd',String(value)));$('comm-result-fields').append(row);}
  $('comm-result-note').textContent=task.result?.error || task.error || (task.state==='succeeded'?'已收到外部电脑返回结果。':task.error?'通信暂时中断，等待恢复后自动接收结果。':terminal.has(task.state)?'请查看完整返回值核对结果。':'正在等待外部电脑返回结果…');
  $('comm-response-raw').hidden=!terminal.has(task.state);$('comm-response-json').textContent=JSON.stringify(task.result||{},null,2);
 }
 const eventNames = {
  queued: 'AGV 已记录请求',
  gateway_response: 'AGV 收到返回结果',
  transport_error: '通信异常',
  request_received: '外部电脑收到请求',
  mes_request: '开始查询 MES',
  mes_response: '收到 MES 返回信息',
  manual_reply: '外部电脑手动返回结果',
  http_return: '向 AGV 返回结果'
 };
 function renderDetail(task, events, warning) {
  const panel = $('comm-record-detail');
  panel.replaceChildren();
  const response = task.result || {};
  panel.append(node('h4', '本次返回值'), node('pre', JSON.stringify(response, null, 2)));
  if (task.error) panel.append(node('p', '通信异常：' + task.error));
  panel.append(node('h4', '关键时间日志'));
  if (warning) panel.append(node('p', warning.startsWith('正在') ? warning : '部分日志暂时无法读取，请稍后重新打开详情。'));
  const keyEvents = events.filter(event => eventNames[event.kind] && event.kind !== 'http_return' &&
   (event.kind !== 'gateway_response' || terminal.has(event.data?.state)))
   .sort((a, b) => a.created - b.created);
  if (!keyEvents.length) panel.append(node('p', '暂无已保存的关键时间日志。'));
  for (const event of keyEvents) {
   const error = event.kind === 'transport_error' ? '：' + (event.data?.error || '连接失败') : '';
   panel.append(node('p', date(event.created) + ' · ' + eventNames[event.kind] + error));
  }
 }
 async function detail(task) {
  selected = task.id;
  result();
  const dialog = $('comm-record-dialog');
  dialog.dataset.taskId = task.id;
  renderDetail(task, (data.events || []).filter(event => event.task_id === task.id), '正在读取本次通信日志…');
  if (!dialog.open) {
   dialog.showModal();
   document.documentElement.classList.add('comm-detail-open');
  }
  $('comm-record-detail').scrollTop = 0;
  try {
   const url = root.dataset.detailUrl.replace('00000000-0000-0000-0000-000000000000', task.id);
   const response = await fetch(url, {cache: 'no-store'});
   const detail = await response.json();
   if (!response.ok || !detail.success) throw Error(detail.error || '详情读取失败');
   if (dialog.dataset.taskId !== task.id || !dialog.open) return;
   renderDetail(detail.task || task, detail.events || [], detail.warning);
  } catch (error) {
   if (dialog.dataset.taskId === task.id && dialog.open) {
    renderDetail(task, (data.events || []).filter(event => event.task_id === task.id), error.message);
   }
  }
 }
 function records(){
  const query=$('comm-filter').value.trim().toLowerCase();$('comm-records').replaceChildren();
  const rows=tasks.slice(0,100).filter(t=>JSON.stringify(t).toLowerCase().includes(query));
  for(const t of rows){const tr=node('tr');tr.append(node('td',date(t.created)),node('td',names[t.action]||t.action),node('td',`${t.payload.rack_code||'—'}${t.payload.product_code?'\n'+t.payload.product_code:''}`));const state=node('td'),badge=node('span',states[t.state]||t.state);badge.className='comm-badge';badge.dataset.state=t.state;state.append(badge);tr.append(state);const action=node('td'),button=node('button','查看详情');button.type='button';button.className='mes-link';button.addEventListener('click',()=>detail(tasks.find(row=>row.id===t.id)||t));action.append(button);tr.append(action);$('comm-records').append(tr);}
  if(!rows.length){const tr=node('tr'),td=node('td','暂无通信记录');td.colSpan=5;td.className='comm-empty';tr.append(td);$('comm-records').append(tr);}
 }
 async function refresh(){
  if(loading)return;loading=true;
  try{const response=await fetch(root.dataset.statusUrl,{cache:'no-store'});if(!response.ok)throw Error();data=await response.json();merge();records();result();}
  catch{data.connected=false;}
  finally{loading=false;$('comm-connection').textContent=data.connected?'外部电脑在线':'外部电脑离线';$('comm-connection').dataset.online=String(!!data.connected);form.querySelector('button').disabled=sending;}
 }
 form.addEventListener('change',()=>{const product=field('action').value==='UPLOAD_PRODUCT_BARCODE';$('comm-product-label').hidden=!product;field('product_code').required=product;});
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(sending)return;sending=true;form.querySelector('button').disabled=true;
  const values={action:field('action').value,rack_code:field('rack_code').value,product_code:field('product_code').value};
  const encoded=JSON.stringify(values);if(encoded!==lastBody||!requestId){requestId=uuid();lastBody=encoded;}
  $('comm-feedback').textContent='正在发送请求…';
  try{const response=await fetch(root.dataset.controlUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({...values,operation:'send',request_id:requestId})});const answer=await response.json();if(!response.ok||!answer.success)throw Error(answer.error||'请求发送失败');selected=answer.id;requestId=null;$('comm-feedback').textContent='请求已发送，正在等待返回。';await refresh();}
  catch{$('comm-feedback').textContent='暂时无法发送，请检查外部电脑连接后重试。';}
  finally{sending=false;form.querySelector('button').disabled=false;}
 });
 $('comm-filter').addEventListener('input',records);$('comm-refresh').addEventListener('click',refresh);$('comm-close-record').addEventListener('click',()=>$('comm-record-dialog').close());
 $('comm-record-dialog').addEventListener('close',()=>document.documentElement.classList.remove('comm-detail-open'));
 const configForm=$('comm-config-form');
 $('comm-config-open').addEventListener('click',async()=>{
  $('comm-config-dialog').showModal();$('comm-config-feedback').textContent='正在读取配置…';
  configForm.querySelector('[type=submit]').disabled=true;
  try{const response=await fetch(root.dataset.configUrl,{cache:'no-store'});const answer=await response.json();if(!response.ok||!answer.success)throw Error(answer.error||'读取失败');configForm.elements.namedItem('gateway_url').value=answer.gateway_url;configForm.elements.namedItem('token').value='';configForm.elements.namedItem('token').required=!answer.token_configured;$('comm-config-feedback').textContent=answer.token_configured?'已配置认证，留空即可保留。':'请填写配对认证。';configForm.querySelector('[type=submit]').disabled=false;}
  catch(e){$('comm-config-feedback').textContent=e.message;}
 });
 $('comm-config-close').addEventListener('click',()=>$('comm-config-dialog').close());
 configForm.addEventListener('submit',async event=>{
  event.preventDefault();const button=configForm.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;
  try{const response=await fetch(root.dataset.configUrl,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':root.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({gateway_url:configForm.elements.namedItem('gateway_url').value,token:configForm.elements.namedItem('token').value})});const answer=await response.json();if(!response.ok||!answer.success)throw Error(answer.error||'保存失败');configForm.elements.namedItem('token').value='';configForm.elements.namedItem('token').required=false;$('comm-config-feedback').textContent=answer.message;await refresh();}
  catch(e){$('comm-config-feedback').textContent=e.message;}
  finally{button.disabled=false;}
 });
 if(new URLSearchParams(window.location.search).get('configure')==='1')$('comm-config-open').click();
 refresh();setInterval(()=>{if(!document.hidden)refresh();},3000);
})();
