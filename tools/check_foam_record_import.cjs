// Regression checks for history import: reuse validated preview and commit only on success.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('templates/vision/foam_inspector_interactive.html', 'utf8');
const start = source.indexOf('let recordImageImportBusy = false;');
const end = source.indexOf('// 弹窗按钮监听', start);
const code = source.slice(start, end);
async function run(response, previewError) {
  const events = [], elements = new Map();
  const context = vm.createContext({
    File, AbortController, setTimeout, clearTimeout,
    document: {getElementById(id) {if (!elements.has(id)) elements.set(id, {}); return elements.get(id);}},
    fetch: async () => {events.push('fetch'); return response;},
    previewImportedFile: async file => {events.push(['preview', file.type, file.name]); if(previewError) throw new Error(previewError);},
    showLoading: () => events.push('loading'), hideLoading: () => events.push('hidden'),
    setPendingBadge: () => events.push('badge'), showDetectionFeedback: () => events.push('feedback'),
    closeRecordsModal: () => events.push('closed'), console: {error(){}},
  });
  vm.runInContext(code, context);
  const card = {dataset: {imgUrl:'/original', time:'2026-11-12 09:51:30', pos:'2'}};
  await context.selectRecordImage(card);
  return {events, elements, context, card};
}
(async () => {
  const valid = {ok:true, blob:async()=>new Blob(['image'], {type:'image/png'})};
  let result = await run(valid);
  assert.equal(result.events.filter(e=>Array.isArray(e)).length,1);
  assert.deepEqual(result.events.find(e=>Array.isArray(e)).slice(0,2),['preview','image/png']);
  assert.match(result.events.find(e=>Array.isArray(e))[2],/\.png$/);
  assert.ok(result.events.includes('closed'));
  result = await run({ok:false,status:404});
  assert.match(result.elements.get('records-modal-guidance').textContent,/原图不存在/);
  assert.ok(!result.events.includes('closed'));
  result = await run(valid,'无法解码图片');
  assert.match(result.elements.get('records-modal-guidance').textContent,/无法解码/);
  assert.ok(!result.events.includes('badge'));
  await result.context.selectRecordImage({...result.card,dataset:{imgUrl:''}});
  assert.match(result.elements.get('records-modal-guidance').textContent,/缺失/);
  console.log('PASS: history import success, 404, decode failure and missing image.');
})().catch(error=>{console.error(error);process.exitCode=1;});
