// Run with node tools/test_offline_canvas_loading.cjs (no hardware or database).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() {
    this.children = []; this.style = {}; this.dataset = {}; this.handlers = {};
    this.value = ''; this.textContent = ''; this.width = 20; this.height = 10;
    this.complete = false; this.naturalWidth = 0;
  }
  addEventListener(name, fn) { (this.handlers[name] ||= []).push(fn); }
  querySelector() { return new Element(); }
  querySelectorAll(selector) { return selector === 'button' ? this.children : []; }
  appendChild(node) { this.children.push(node); }
  replaceChildren() { this.children = []; }
  before() {} after() {} setAttribute() {}
  getBoundingClientRect() { return {width: 20, height: 10}; }
  getContext() { return new Proxy({}, {get: () => () => {}}); }
}
function setup({previewComplete = false, fail = false, decodeFail = false} = {}) {
  const nodes = {}, get = id => nodes[id] ||= new Element();
  get('dp-rack-layers').value = '3'; get('recipe-select').value = '7';
  get('rack-workbench').dataset.mode = 'dual';
  get('dp-panel').dataset.prepareUrl = '/prepare';
  get('rl-depth-image').complete = previewComplete;
  get('rl-depth-image').naturalWidth = previewComplete ? 20 : 0;
  let frame = {}, calls = 0;
  const bridge = {snapshot: () => frame, load: payload => { frame = payload; }};
  const window = {rackLocatorOfflineBridge: bridge, addEventListener() {}};
  vm.runInNewContext(fs.readFileSync('static/vision/js/rack_dual_point.js', 'utf8'), {
    document: {getElementById: get, createElement: () => new Element(), querySelector: get},
    window, MutationObserver: class { observe() {} },
    Image: class {
      constructor() { this.naturalWidth = 20; this.naturalHeight = 10; }
      async decode() { if (decodeFail) throw new Error('原图解码失败'); }
    },
    fetch: async (url, options) => {
      calls++;
      assert.ok(options.body.length < 10000, 'must not post saved template points or historical results');
      const body = JSON.parse(options.body);
      assert.ok(body.pointcloud_token);
      assert.equal(body.roi_config, undefined);
      assert.equal(body.result, undefined);
      return {ok: !fail, json: async () => fail ? {success: false, errorMessage: '缺少原图'} : {
        success: true, image_url: '/original', depth_preview_url: '/depth', width: 20, height: 10,
        config: {imageSize: [20, 10], rack_layers: 3,
          rois: [{target: 'P1_cross', x: 1, y: 1, width: 5, height: 5}]},
        image_token: 'image', cloud_token: 'cloud', three_d_status: '就绪'
      }};
    },
    setTimeout,
  });
  return {bridge, get, calls: () => calls};
}
(async () => {
  for (const previewComplete of [false, true]) {
    const app = setup({previewComplete});
    await app.bridge.load({pointcloud_token: 'frame1',
      roi_config: {cloud_center_reference: {points: 'x'.repeat(4 * 1024 * 1024)}},
      result: {diagnostics: 'x'.repeat(1024 * 1024)}});
    assert.equal(app.calls(), 1, 'prepare must run even if hidden preview never loads');
    assert.equal(app.get('dp-canvas').hidden, false);
    assert.match(app.get('dp-frame-status').textContent, /已载入画布/);
    assert.equal(app.bridge.snapshot().roi_config.cloud_center_config.rois.length, 1);
    await app.bridge.load({pointcloud_token: 'frame2'});
    assert.equal(app.calls(), 2);
    assert.equal(app.bridge.snapshot().pointcloud_token, 'frame2');
  }
  for (const options of [{fail: true}, {decodeFail: true}]) {
    const app = setup(options);
    await assert.rejects(app.bridge.load({pointcloud_token: 'bad'}), /加载画布失败/);
    assert.match(app.get('dp-frame-status').textContent, /加载画布失败/);
    assert.equal(app.get('dp-canvas').hidden, true);
  }
  const app = setup();
  const first = app.bridge.load({pointcloud_token: 'first'});
  await assert.rejects(app.bridge.load({pointcloud_token: 'second'}), /当前操作尚未完成/);
  await first;
  assert.equal(app.bridge.snapshot().pointcloud_token, 'first');
  console.log('PASS: missing/cached previews, ROI restoration, repeated loads, errors and concurrent load guard');
})().catch(error => { console.error(error); process.exitCode = 1; });
