(() => {
  'use strict';
  const $ = id => document.getElementById(`fs-${id}`);
  const api = document.getElementById('foam-stream').dataset.api;
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  let mode='video', token=null, metadata=null, playing=false, busy=false, generation=0, timer=null, liveTimer=null;
  let config={}, events={}, previousFrameAt=0;
  let opening=false, liveBusy=false, lastLiveResponse=0;
  const waitForFrame=async()=>{while(busy)await new Promise(resolve=>setTimeout(resolve,20));};
  const labels={NORMAL:'正常展开',FALLEN:'倒伏 NG',UNKNOWN:'未确认'};
  const clock=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${String(Math.floor(t%60)).padStart(2,'0')}`;
  function error(message='') { $('error').textContent=message; $('error').hidden=!message; }
  async function request(path, body, method='POST') {
    const options={method,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(8000),headers:{'X-CSRFToken':csrf}};
    if(body instanceof FormData) options.body=body;
    else if(method!=='GET') {options.headers['Content-Type']='application/json';options.body=JSON.stringify(body||{});}
    const response=await fetch(api+path,options);
    let data;
    try {data=await response.json();} catch {throw new Error(`服务返回异常（HTTP ${response.status}），请检查后台服务`);}
    if(!response.ok||!data.success) throw new Error(data.error||`请求失败：${response.status}`);
    return data;
  }
  function pause() {playing=false;clearTimeout(timer);$('play').textContent='播放并检测';$('overlay').hidden=!token;$('overlay').textContent='已暂停';}
  function resetDisplay() {
    events={}; previousFrameAt=0;
    $('events').replaceChildren();$('events').textContent='本次尚未确认倒伏。';$('event-count').textContent='0 次';
    $('verdict').className='fs-verdict unknown';$('verdict-text').textContent='待检测';$('verdict-reason').textContent='等待有效画面';
    for(const side of ['left','right']) {$(`${side}`).textContent='未确认';$(`${side}-detail`).textContent='等待有效画面';}
    $('view').textContent='—';$('latency').textContent='—';$('fps').textContent='—';
  }
  function render(data) {
    const r=data.result;
    if(data.image){$('image').src=data.image;$('image').hidden=false;$('empty').hidden=true;}
    if(!r)return;
    $('verdict').className=`fs-verdict ${r.state==='NORMAL'?'normal':r.state==='FALLEN'?'fallen':'unknown'}`;
    $('verdict-text').textContent=r.state==='FALLEN'?'NG · 检出倒伏':r.state==='NORMAL'?'OK · 正常展开':'未确认';
    $('verdict-reason').textContent=r.state==='FALLEN'?'当前检出倒伏 NG，后续检测结果自动更新。':r.state==='NORMAL'?'左右泡棉均通过多帧确认。':'等待清晰且定位可靠的连续画面，不输出 OK。';
    for(const side of ['left','right']) {
      const s=r.sides[side];if(!s)continue;
      $(side).textContent=labels[s.state]||s.state;
      $(`${side}-detail`).textContent=s.state==='UNKNOWN'&&s.observation!=='UNKNOWN'?`${labels[s.observation]}，确认 ${s.votes}/3 帧`:s.reason||'等待确认';
    }
    $('view').textContent=r.registration.status==='REGISTERED'?`${r.registration.view==='far'?'远端':r.registration.view==='near'?'近端':r.registration.view} · 已定位`:'定位不足';
    $('latency').textContent=`${r.elapsed_ms.toFixed(1)} ms`;
    const now=performance.now();if(previousFrameAt&&playing)$('fps').textContent=`${(1000/(now-previousFrameAt)).toFixed(1)} fps`;previousFrameAt=now;
    if(mode==='video'&&metadata){$('time').textContent=`${clock(r.timestamp)} / ${clock(metadata.duration)}`;$('seek').value=r.frame_id;$('frame').textContent=`第 ${r.frame_id+1} 帧`;}
    for(const [side,t] of Object.entries(r.first_ng||{})) if(!(side in events)){
      if(!Object.keys(events).length)$('events').replaceChildren();events[side]=t;
      const row=document.createElement('div');row.className='fs-event';const stamp=document.createElement('time');stamp.textContent=`${t.toFixed(2)}s`;
      const text=document.createElement('span');text.textContent=`${side==='left'?'左侧':side==='right'?'右侧':side}泡棉 · 确认倒伏`;
      row.append(stamp,text);$('events').append(row);$('event-count').textContent=`${Object.keys(events).length} 次`;
    }
  }
  async function closeCurrent(){if(token){const old=token;token=null;try{await request(`video/${old}/close/`);}catch{}}}
  async function openVideo(body){
    if(opening)return;opening=true;
    pause();generation++;const gen=generation;error();$('import').disabled=true;
    try{await waitForFrame();await closeCurrent();const data=await request('video/',body);if(gen!==generation){await request(`video/${data.session}/close/`);return;}
      token=data.session;metadata=data;resetDisplay();$('source').textContent=data.filename;$('connection').textContent=`${data.fps.toFixed(2)} fps · 视频调试`;
      $('seek').max=data.frames-1;$('seek').disabled=false;for(const b of ['play','step','restart'])$(b).disabled=false;
      playing=true;$('play').textContent='暂停';$('overlay').hidden=true;await nextFrame();
    }catch(e){error(e.message);}finally{$('import').disabled=false;opening=false;}
  }
  async function nextFrame(seek){
    if(!token||busy)return;
    busy=true;const gen=generation,start=performance.now();
    try{const data=await request(`video/${token}/frame/`,seek===undefined?{}:{seek});
      if(gen!==generation)return;
      if(data.ended){pause();$('overlay').textContent='播放结束';$('connection').textContent='回放完成';return;}
      $('connection').textContent=playing?`${metadata.fps.toFixed(2)} fps · 视频调试`:'已暂停 · 视频调试';
      render(data);error();
    }catch(e){if(gen===generation){pause();error(e.message);}}
    finally{busy=false;if(playing&&gen===generation)timer=setTimeout(()=>nextFrame(),Math.max(0,1000/(metadata.fps*Number($('speed').value))-(performance.now()-start)));}
  }
  async function setMode(next){
    if(next===mode)return;
    pause();clearTimeout(liveTimer);generation++;mode=next;
    for(const name of ['video','live']){$(`${name}-tab`).classList.toggle('active',name===next);$(`${name}-tab`).setAttribute('aria-selected',String(name===next));$(`${name}-controls`).hidden=name!==next;}
    $('mode-label').textContent=next==='video'?'调试模式 · 不回写 PLC':'海康相机 · 服务器连续检测';
    $('plc').textContent='仅检测，不回写 PLC';
    $('empty-title').textContent=next==='live'?'等待相机实时画面':'导入视频，边播放边检测';
    $('empty-help').textContent=next==='live'?'连接相机后持续采集和检测，无需导入视频':'支持 AVI、MP4、MOV、MKV · 最大 256 MB';
    resetDisplay();$('image').hidden=true;$('empty').hidden=false;$('overlay').hidden=true;
    if(next==='live') {await waitForFrame();await closeCurrent();pollLive();}else{$('source').textContent='等待导入视频';$('connection').textContent='未连接';for(const b of ['play','step','restart','seek'])$(b).disabled=true;}
  }
  function invalidateLive(message) {
    $('verdict').className='fs-verdict unknown';$('verdict-text').textContent='未确认';$('verdict-reason').textContent=message;
    for(const side of ['left','right']) {$(side).textContent='未确认';$(`${side}-detail`).textContent='等待有效画面';}
    $('view').textContent=$('fps').textContent=$('latency').textContent='—';
  }
  function renderLive(data) {
    $('source').textContent='海康 2D 相机';
    $('connection').textContent=data.error?'相机异常 / 正在重连':data.running?'持续采集中':'等待相机启动';
    $('mode-label').textContent=data.manual?'手动连续调试 · 自动工序已暂停':'自动监控 · 持续采集与检测';
    $('start-live').disabled=liveBusy||data.manual;
    $('stop-live').disabled=liveBusy||!data.manual;
    if(data.generation!==config.liveGeneration){resetDisplay();config.liveGeneration=data.generation;}
    render({...data,image:$('annotated').checked?data.result_image:data.image});
    if(data.stale)invalidateLive('暂无有效检测结果，请检查相机连接及算法状态');
    else $('fps').textContent=`${data.processing_fps.toFixed(1)} fps`;
    if(data.preview_stale||($('annotated').checked&&data.stale)) {
      $('image').hidden=true;$('empty').hidden=false;
    }
    error(data.error||data.processing_error||'');
  }
  async function pollLive(){
    if(mode!=='live')return;
    const gen=generation;
    try{const data=await request('live/',null,'GET');if(mode!=='live'||gen!==generation)return;
      lastLiveResponse=Date.now();renderLive(data);
    }catch(e){if(mode==='live'&&gen===generation){invalidateLive('连续检测服务连接中断');$('image').hidden=true;$('empty').hidden=false;error(e.message);}}
    finally{if(mode==='live'&&gen===generation)liveTimer=setTimeout(pollLive,100);}
  }
  setInterval(()=>{if(mode==='live'&&lastLiveResponse&&Date.now()-lastLiveResponse>2500){
    invalidateLive('相机状态已过期，等待重新连接');$('image').hidden=true;$('empty').hidden=false;
  }},500);
  $('import').onclick=()=>$('file').click();
  $('file').onchange=()=>{const file=$('file').files[0];if(!file)return;if(file.size>256*1024*1024){error('视频文件不能超过 256 MB');return;}const form=new FormData();form.append('video',file);openVideo(form);$('file').value='';};
  $('play').onclick=()=>{if(playing)pause();else{playing=true;$('play').textContent='暂停';$('overlay').hidden=true;nextFrame();}};
  $('step').onclick=()=>{pause();nextFrame();};
  $('restart').onclick=async()=>{pause();await waitForFrame();resetDisplay();playing=true;$('play').textContent='暂停';$('overlay').hidden=true;nextFrame(0);};
  $('seek').onchange=async()=>{const target=Number($('seek').value);pause();await waitForFrame();resetDisplay();nextFrame(target);};
  $('video-tab').onclick=()=>setMode('video');$('live-tab').onclick=()=>setMode('live');
  for(const [id,action] of [['start-live','enter_manual'],['stop-live','resume_auto'],['reset-live','reset']])$(id).onclick=async()=>{
    if(liveBusy)return;liveBusy=true;for(const key of ['start-live','stop-live','reset-live'])$(key).disabled=true;
    try{const data=await request('live/control/',{action});if(mode==='live')renderLive(data);error();}
    catch(e){error(e.message);}finally{liveBusy=false;$('reset-live').disabled=false;}
  };
  window.addEventListener('pagehide',()=>{pause();if(token){const body=new FormData();body.append('csrfmiddlewaretoken',csrf);navigator.sendBeacon(api+`video/${token}/close/`,body);}});
  request('config/',null,'GET').then(data=>{config=data;$('profile-name').textContent=data.profile_name||'未配置标准模板';$('profile-scope').textContent=data.scope;
    if(!data.ready)error('请先配置正常泡棉模板，再开始连续检测。');
    for(const name of data.samples){const button=document.createElement('button');button.textContent=name;button.onclick=()=>openVideo({sample:name});$('samples').append(button);}
  }).catch(e=>error(e.message));
})();
