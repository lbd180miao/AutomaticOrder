const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('static/vision/js/rack_locator_workbench.js', 'utf8');
const template = fs.readFileSync('templates/vision/rack_locator_panel.html', 'utf8');
function section(text, start, end) {
  return text.slice(text.indexOf(start), text.indexOf(end, text.indexOf(start)));
}

test('ROI round trip uses pointcloud pixels even when preview resolution differs', () => {
  const context = vm.createContext({
    image: {naturalWidth: 640, naturalHeight: 480, dataset: {naturalWidth: '1280', naturalHeight: '960'}},
    canvas: {width: 320, height: 240},
  });
  vm.runInContext(section(source, '  function naturalDims()', '  function setReadout()')
    + section(source, '  function realToDisplay(', '  function drawLayerSpacingLineOverlay('), context);
  const roi = vm.runInContext('displayToReal({x: 20, y: 30, w: 100, h: 80})', context);
  assert.deepEqual(JSON.parse(JSON.stringify(roi)), {x: 80, y: 120, w: 400, h: 320});
  context.roi = roi;
  context.canvas = {width: 640, height: 480};
  assert.equal(vm.runInContext('realToDisplay(roi).x', context), 40);
  assert.equal(vm.runInContext('realPointToDisplay({x:80,y:120}).y', context), 60);
});

test('late recipe response cannot overwrite a newly drawn ROI or another recipe', async () => {
  for (const change of ['edit', 'recipe']) {
    let resolveDetail;
    let revision = 0;
    let id = '1';
    let applied = 0;
    const context = vm.createContext({URLSearchParams, console,
      document: {getElementById: () => ({value: id})},
      window: {rackLocatorRoiRevision: () => revision, rackLocatorSetRoi: () => applied++},
      fetch: async url => ({headers: {get: () => 'application/json'}, json: () =>
        url.includes('?id=') ? new Promise(resolve => {resolveDetail = resolve;}) : Promise.resolve({success:true,data:{rois:[]}})}),
    });
    vm.runInContext(section(template, '  let recipeRoiLoadSeq', '  // ── 在画布上显示 ROI'), context);
    const loading = vm.runInContext('loadRecipeRoi("1")', context);
    while (!resolveDetail) await new Promise(resolve => setImmediate(resolve));
    if (change === 'edit') revision++; else id = '2';
    resolveDetail({success:true, recipes:[{roi_config:{target_roi:{x:1,y:2,w:3,h:4}}}]});
    await loading;
    assert.equal(applied, 0);
  }
});

test('saving ROI preserves recipe metadata and serializes successive edits', async () => {
  const calls = [];
  const context = vm.createContext({
    $: () => ({value:'7'}), CFG: {recipeApiUrl:'/recipes/'}, state:{},
    roiSaveRequestSeq:0, roiEditRevision:0, roiSaveChain:Promise.resolve(),
    measurementConfigPatch: () => ({target_roi:{x:10,y:20,w:30,h:40}}),
    measurementConfigSummary: () => ({labels:['外框'],count:1}),
    setStatus: () => {}, apiPayload: value => value,
    postJson: async (url, payload, method) => {calls.push({payload,method}); return {success:true};},
  });
  vm.runInContext(section(source, '  async function autoSaveRoiToRecipe(', '  // ── 自动选中下一个配方'), context);
  await vm.runInContext('Promise.all([autoSaveRoiToRecipe(), autoSaveRoiToRecipe()])', context);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].method, 'PATCH');
  assert.deepEqual(Object.keys(calls[0].payload).sort(), ['id','roi_config']);
});

test('initial refresh resolves the selected recipe by ID, never by layer', async () => {
  const nodes = {'recipe-select': {value:'9'}, 'recipe-id': {value:'2'}};
  const urls = [];
  const context = vm.createContext({URLSearchParams, console,
    $: id => nodes[id], CFG:{recipeApiUrl:'/recipes/',currentRecipeUrl:'/current/'},
    state:{recipeRequestSeq:0}, roiSaveRequestSeq:0,
    fetch: async url => { urls.push(url); return {json: async () => ({recipes:[{id:9,roi_config:{}}]})}; },
    apiPayload: value => value, syncRansacThreshold: () => {},
    renderLocalTemplate: () => {}, renderLayerSpacing: () => {},
  });
  vm.runInContext(section(source, '  async function refreshCurrentRecipe(', '  function cleanTargetRoi('), context);
  await vm.runInContext('refreshCurrentRecipe()', context);
  assert.deepEqual(urls, ['/recipes/?id=9']);
  assert.equal(nodes['recipe-id'].value, 9);
  assert.equal(context.state.currentRecipe.id, 9);
});

test('loading an old package uses saved recipe ROI and preserves unsaved redraws', async () => {
  const fresh = {x:100,y:200,w:300,h:400};
  let reads = 0;
  const context = vm.createContext({console, roiEditRevision:1,
    state:{token:'cloud',roiDirty:false}, image:{src:'preview',style:{}},
    $: () => ({value:'9'}), CFG:{recipeApiUrl:'/recipes/'}, window:{},
    fetch: async () => {reads++; return {ok:true,json:async () => ({success:true,recipes:[{id:9,roi_config:{target_roi:fresh}}]})};},
    apiPayload:value=>value, applyLocalTemplateRois:()=>{}, applyLayerSpacingLine:()=>{},
    syncRansacThreshold:()=>{}, draw:()=>{}, setReadout:()=>{}, refreshActionState:()=>{},setStatus:()=>{},
    applyPixelRoi:roi=>{context.state.roi=roi;},
  });
  vm.runInContext(section(source, '  async function autoLoadAndShowRecipeRoi(', '  function afterPreviewLoaded('), context);
  await vm.runInContext('autoLoadAndShowRecipeRoi({recipeId:2,targetRoi:{x:1,y:1,w:2,h:2}})',context);
  assert.equal(context.state.roi, fresh);
  context.state.roiDirty = true;
  const draft = {x:10,y:20,w:30,h:40};
  context.state.roi = draft;
  await vm.runInContext('autoLoadAndShowRecipeRoi({recipeId:2})',context);
  assert.equal(context.state.roi,draft);
  assert.equal(reads,1);
});

test('redrawing is a local draft and full save includes cleared positions', () => {
  const context = vm.createContext({roiEditRevision:0,state:{},window:{},
    $:()=>({}),setStatus:()=>{},refreshActionState:()=>{},
    cleanTargetRoi:()=>null, cleanLocalTemplateRois:()=>({plane1:null,plane2:{x:1,y:2,w:3,h:4},plane3:null}),
    cleanLayerSpacingLine:()=>null, selectedRansacThreshold:()=>2,
  });
  vm.runInContext(section(source,'  function markRoiEdited()', '  // ── 暴露设置 ROI'),context);
  vm.runInContext(section(source,'  function measurementConfigPatch(', '  function measurementConfigSummary('),context);
  vm.runInContext('markRoiEdited()',context);
  assert.equal(context.state.roiDirty,true);
  const saved=vm.runInContext('measurementConfigPatch("all")',context);
  assert.equal(saved.target_roi,null);
  assert.equal(saved.local_template_rois.plane1,null);
  assert.equal(saved.layer_spacing_line,null);
});

test('drag replaces old ROI, only Save sends new coordinates, reload keeps them', async () => {
  const events = {};
  let persisted = {x:1,y:2,w:3,h:4};
  let writes = 0;
  const button = {addEventListener: (event, fn) => {events.save = fn;}};
  const context = vm.createContext({console, roiEditRevision:0,roiSaveRequestSeq:0,roiSaveChain:Promise.resolve(),
    state:{token:'frame',roi:persisted,drawMode:'rect',invalidRoiKeys:[]},
    canvas:{style:{},addEventListener:(event,fn)=>{events[event]=fn;}},
    window:{addEventListener:(event,fn)=>{events[event]=fn;}},
    image:{src:'preview',style:{}}, CFG:{recipeApiUrl:'/recipes/'},
    $:id=>id==='btn-save-recipe'?button:{value:'9'},
    draw:()=>{},refreshActionState:()=>{},setStatus:()=>{},setReadout:()=>{},syncRoiToRightSide:()=>{},
    pointerToCanvas:event=>({x:event.clientX,y:event.clientY}), displayToReal:value=>value,
    measurementConfigSummary:()=>({count:1,labels:['外框']}),
    measurementConfigPatch:()=>({target_roi:context.state.roi}),apiPayload:value=>value,
    postJson:async (url,payload)=>{writes++;persisted=JSON.parse(JSON.stringify(payload.roi_config.target_roi));return {success:true,recipe:{id:9,roi_config:{target_roi:persisted}}};},
    fetch:async()=>({ok:true,json:async()=>({success:true,recipes:[{id:9,roi_config:{target_roi:persisted}}]})}),
    applyLocalTemplateRois:()=>{},applyLayerSpacingLine:()=>{},syncRansacThreshold:()=>{},
    applyPixelRoi:roi=>{context.state.roi=roi;},
  });
  vm.runInContext(section(source,'  function markRoiEdited()', '  // ── 暴露设置 ROI')
    + section(source,"  canvas.addEventListener('mousedown'",'  // ── 多边形画笔模式')
    + section(source,"  $('btn-save-recipe')?.addEventListener",'  // ── 采集点云')
    + section(source,'  async function autoSaveRoiToRecipe(', '  // ── 自动选中下一个配方')
    + section(source,'  async function autoLoadAndShowRecipeRoi(', '  function afterPreviewLoaded('),context);
  events.mousedown({button:0,clientX:100,clientY:200});
  events.mousemove({clientX:150,clientY:260});
  events.mouseup();
  assert.equal(writes,0);
  assert.equal(context.state.roi.x,100);
  assert.equal(context.state.roiDirty,true);
  await events.save();
  assert.equal(writes,1);
  assert.equal(persisted.w,50);
  assert.equal(context.state.roiDirty,false);
  context.state.roi=null;
  await vm.runInContext('autoLoadAndShowRecipeRoi({targetRoi:{x:1,y:2,w:3,h:4}})',context);
  assert.equal(context.state.roi.x,100);
  assert.equal(context.state.roi.h,60);
});
