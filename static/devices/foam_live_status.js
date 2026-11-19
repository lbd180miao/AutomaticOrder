(() => {
  'use strict';
  const root=document.getElementById('device-foam-live');if(!root)return;
  const field=name=>root.querySelector(`[data-foam="${name}"]`);
  const labels={NORMAL:'正常展开',FALLEN:'倒伏 NG',UNKNOWN:'未确认'};
  let lastFrame='',lastResponse=0;
  function unavailable(message,keepPreview=false){
    field('verdict').hidden=true;field('sides').hidden=true;field('no-data').hidden=false;
    field('connection').textContent=message;
    field('left').textContent=field('right').textContent='未确认';
    if(!keepPreview){field('image').hidden=true;field('empty').hidden=false;field('empty').textContent='暂无相机画面';lastFrame='';}
    field('empty').title=message;
    field('metrics').textContent='暂无新鲜有效检测结果';
  }
  function render(data){
    const result=data.result;
    const hasPreview=Boolean(data.running&&!data.error&&!data.preview_stale&&data.image);
    if(hasPreview){
      if(data.image!==lastFrame){field('image').src=data.image;lastFrame=data.image;}
      field('image').hidden=false;field('empty').hidden=true;
    }else{
      field('image').hidden=true;field('empty').hidden=false;field('empty').textContent='暂无相机画面';lastFrame='';
    }
    field('error').textContent=data.error||data.processing_error||'';field('error').hidden=!(data.error||data.processing_error);
    if(!data.running||data.stale||data.error||!result){
      unavailable(data.error?'相机断流 / 正在重连':data.stopping?'相机正在停止':hasPreview?'相机实时采集 · 等待有效检测结果':data.running?'相机已启动，等待有效画面':'连续检测未运行',hasPreview);
      field('detail').textContent=result?.state==='FALLEN'?'当前画面不可用，已保存的 NG 日志仍保留。':'连续检测不依赖 68.4；可在工作台检查连接或启动相机。';
      return;
    }
    field('connection').textContent='● 相机持续采集 · 算法实时检测';
    field('verdict').hidden=false;field('sides').hidden=false;field('no-data').hidden=true;
    field('verdict').textContent=result.state==='FALLEN'?'NG':result.state==='NORMAL'?'OK':'未确认';
    field('verdict').className='inspection-verdict '+(result.state==='FALLEN'?'fail':result.state==='NORMAL'?'pass':'');
    for(const side of ['left','right'])field(side).textContent=labels[result.sides?.[side]?.state]||'未确认';
    field('detail').textContent=result.state==='FALLEN'?'当前检出倒伏 NG，已记录日志，后续检测结果自动更新。':result.state==='NORMAL'?'左右泡棉均通过多帧确认，正常展开。':'定位或形态证据不足，等待多帧确认，不判 OK。';
    field('metrics').textContent=`帧 ${result.frame_id} · 算法 ${result.elapsed_ms.toFixed(1)} ms · 画面延迟 ${Math.round(data.age_seconds*1000)} ms`;
  }
  field('image').addEventListener('error',()=>unavailable('相机画面解码失败'));
  async function poll(){
    try{
      if(!document.hidden){
        const response=await fetch(root.dataset.url,{cache:'no-store',signal:AbortSignal.timeout(3000)});
        if(!response.ok)throw new Error(`HTTP ${response.status}`);
        const data=await response.json();if(!data.success)throw new Error(data.error||'状态读取失败');
        lastResponse=Date.now();render(data);
      }
    }catch(error){unavailable('连续检测服务连接中断');field('error').textContent=error.message;field('error').hidden=false;}
    finally{setTimeout(poll,250);}
  }
  // Invalidate an old OK even while a status request is waiting for timeout.
  setInterval(()=>{if(lastResponse&&Date.now()-lastResponse>2500)unavailable('相机状态已过期，等待重新连接');},500);
  field('reset').onclick=async()=>{
    field('reset').disabled=true;
    try{
      const response=await fetch(root.dataset.control,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify({action:'reset'}),signal:AbortSignal.timeout(4000)});
      const data=await response.json();if(!response.ok||!data.success)throw new Error(data.error||'重置失败');render(data);
    }catch(error){field('error').textContent=error.message;field('error').hidden=false;}
    finally{field('reset').disabled=false;}
  };
  poll();
})();
