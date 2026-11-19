(() => {
  'use strict';
  const $=id=>document.getElementById('rp-'+id), root=document.getElementById('rivet-recipes');
  const api='/vision/api/vision/3d/recipes/', defaults='/vision/api/recipes/plc-defaults/';
  const csrf=document.querySelector('[name=csrfmiddlewaretoken]').value;
  let recipes=[],editId=null,copyId=null;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=v=>Number.isFinite(v)?v.toFixed(3):'—';
  const xyz=v=>Array.isArray(v)&&v.length===3?v.map(num).join(' / '):'—';
  const note=(message,bad=false)=>{ $('message').textContent=message;$('message').className=bad?'rp-missing':'rp-ready';};
  async function request(url,body,method='GET') {
    const options={method,headers:{'X-CSRFToken':csrf},cache:'no-store'};
    if(body instanceof FormData)options.body=body;
    else if(body!==undefined){options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
    const response=await fetch(url,options),data=await response.json();
    if(!response.ok||!data.success)throw new Error(data.error||data.error_message||'请求失败');
    return {...data,...data.data};
  }
  function table(headers,rows){return `<div class="rp-table"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
  function details(recipe){
    const summary=recipe.rivet_template||{},config=recipe.roi_config?.cloud_center_config||{},ref=recipe.roi_config?.cloud_center_reference||{};
    const names=Number(recipe.layer_count ?? config.rack_layers)===2?['P1','P3']:['P1','P2','P3'];
    const rows=names.map(name=>{
      const roi=summary.rois?.find(r=>r.target===name+'_rivet'),point=summary.points?.find(p=>p.name===name);
      const detection=ref.measurement?.detections?.find(d=>d.name===name),m=detection?.measurement;
      return [name==='P3'?'铆钉 3 · 固定参照':`铆钉 ${name.slice(1)} · 横杆`,roi?`${roi.x} / ${roi.y} / ${roi.width??roi.w} / ${roi.height??roi.h}`:'未框选',xyz(point?.xyz),
        num(point?.score??detection?.candidates?.[0]?.score),`${point?.valid_count??m?.valid_count??'—'} / ${point?.sample_count??m?.sample_count??'—'}`,
        point?.status||m?.status||'未示教'];
    });
    const relative=names.filter(n=>n!=='P3').map((name,i)=>[`${name} − P3`,xyz(summary.relative_vectors?.[i]),i===0?'A':'B']);
    return `<p class="${summary.ready?'rp-ready':'rp-missing'}">${summary.ready?'标准模板已就绪':esc((summary.issues||['待示教']).join('；'))}</p>
      <h3>铆钉标准模板 · 相机坐标系</h3>${table(['铆钉','ROI x / y / 宽 / 高（px）','标准 X / Y / Z（mm）','检测分（非概率）','有效点 / 采样点','状态'],rows)}
      <h3>相机坐标系标准相对向量</h3>${table(['参照关系','相对 X / Y / Z（mm）','PLC 机器人补偿组'],relative)}
      <p class="rp-note">算法：${esc(summary.version||'待建立铆钉模板')} · 图像尺寸：${esc(summary.image_size?.join(' × ')||'—')} · 保存时间：${esc(summary.taught_at||'—')}<br>模板拍照姿态：${summary.robot_transform_context?'已保存':'未保存，发送 PLC 前需有效手眼标定与拍照姿态'}<br>补偿限值：X ±${num(recipe.max_offset_x)} / Y ±${num(recipe.max_offset_y)} / Z ±${num(recipe.max_offset_z)} mm</p>`;
  }
  function render(){
    const query=$('search').value.trim().toLowerCase(),open=new Set([...$('list').querySelectorAll('details[open]')].map(e=>e.dataset.id));
    const shown=recipes.filter(r=>`${r.recipe_name} ${r.rack_type}`.toLowerCase().includes(query));
    $('list').innerHTML=shown.map(r=>`<details class="rp-card ${r.enabled?'':'rp-disabled'}" data-id="${r.id}" ${open.has(String(r.id))?'open':''}>
      <summary><strong class="rp-name">${esc(r.recipe_name)}</strong><span class="rp-layer">${r.layer_count} 层料架配方</span><span class="rp-badge">料架号：${esc(r.rack_type||'未设置')}</span>
      <span class="rp-status ${r.enabled?'enabled':''}">${r.enabled?'✔ 已启用':'✕ 已禁用'}</span><span class="rp-template ${r.rivet_template?.ready?'rp-ready':'rp-missing'}">${r.rivet_template?.ready?'模板就绪':'需示教'}</span>
      <div class="rp-actions rp-row-actions"><button type="button" data-action="edit" data-id="${r.id}">编辑配方 / 限值</button><button type="button" data-action="copy" data-id="${r.id}">增加（复制）</button><button type="button" data-action="export" data-id="${r.id}">导出 JSON</button><button type="button" data-action="delete" data-id="${r.id}">删除</button></div></summary>
      <div class="rp-body">${details(r)}<div class="rp-actions"><a class="btn btn-primary" href="${root.dataset.workbench}?recipe_id=${r.id}">进入 3D 工作台 · 示教 / 检测</a></div></div></details>`).join('')||'<div class="rp-empty">暂无匹配配方，请新增配方。</div>';

  }
  async function load(){
    const [data,selected]=await Promise.all([request(api),request(defaults)]);recipes=data.recipes||[];
    $('default').replaceChildren(new Option('未选择',''));
    recipes.filter(r=>r.enabled).forEach(r=>$('default').add(new Option(r.recipe_name,String(r.id))));
    $('default').value=selected.rack_recipe_id||'';render();
  }
  function edit(recipe=null,copy=false){
    editId=copy?null:recipe?.id;copyId=copy?recipe.id:null;$('form').reset();
    const values={recipe_name:'',rack_type:'',layer_count:3,layer_no:1,position_no:1,enabled:true,max_offset_x:10,max_offset_y:10,max_offset_z:10,...recipe};
    if(copy)values.recipe_name+=' - 副本';
    for(const el of $('form').elements)if(el.name&&values[el.name]!==undefined)el.value=String(values[el.name]);
    $('title').textContent=copy?'复制铆钉配方':recipe?'编辑铆钉配方':'新增铆钉配方';$('dialog').showModal();
  }
  $('create').onclick=()=>edit();$('cancel').onclick=()=>$('dialog').close();$('search').oninput=render;
  $('form').onsubmit=async e=>{
    e.preventDefault();const body=Object.fromEntries(new FormData($('form')));
    for(const key of ['layer_count','layer_no','position_no','max_offset_x','max_offset_y','max_offset_z'])body[key]=Number(body[key]);
    if(body.layer_no>body.layer_count){note('检测层号不能超过料架层数',true);return;}
    body.enabled=body.enabled==='true';if(editId)body.id=editId;if(copyId)body.source_recipe_id=copyId;
    $('save').disabled=true;
    try{await request(api,body,editId?'PATCH':'POST');$('dialog').close();await load();note('配方已保存。修改层数或 ROI 后请重新示教标准模板。');
    }catch(error){note(error.message,true);}finally{$('save').disabled=false;}
  };
  $('default').onchange=async()=>{try{await request(defaults,{kind:'rack',recipe_id:Number($('default').value)},'POST');note('PLC 默认 3D 配方已更新');}catch(e){note(e.message,true);await load();}};
  $('list').onclick=async event=>{
    const button=event.target.closest('[data-action]');if(!button)return;
    event.preventDefault();
    const recipe=recipes.find(r=>r.id===Number(button.dataset.id));if(!recipe)return;
    const action=button.dataset.action;
    if(action==='edit'||action==='copy'){edit(recipe,action==='copy');return;}
    if(action==='delete'&&!confirm(`删除配方「${recipe.recipe_name}」？`))return;
    button.disabled=true;
    try{
      if(action==='delete'){await request(api,{id:recipe.id},'DELETE');await load();note('配方已删除');}
      else if(action==='export'){
        const response=await fetch(`/vision/api/recipes/transfer/rack3d/${recipe.id}/export/`);if(!response.ok)throw new Error('导出失败');
        const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=`rivet-recipe-${recipe.id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      }
    }catch(e){note(e.message,true);}finally{button.disabled=false;}
  };
  $('import').onclick=()=>$('file').click();$('file').onchange=async()=>{
    const file=$('file').files[0];$('file').value='';if(!file)return;
    if(file.size>32*1024*1024){note('文件不得超过 32 MB',true);return;}
    const body=new FormData();body.append('file',file);$('import').disabled=true;
    try{const data=await request('/vision/api/recipes/transfer/rack3d/import/',body,'POST');await load();note(`已导入「${data.name}」\n${(data.warnings||[]).join('\n')}`);}catch(e){note(e.message,true);}finally{$('import').disabled=false;}
  };
  load().catch(e=>{note(e.message,true);$('list').textContent='配方读取失败';});
})();
