// Run against the local workbench. All writes are blocked; no camera/PLC calls.
const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'D:/Scripts/FrciblyK12/.venv/Lib/site-packages/playwright/driver/package');
(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => route.request().method() === 'POST'
      ? route.abort() : route.continue());
    await page.goto('http://127.0.0.1:8082/vision/foam-inspector/');
    await page.locator('#btn-start-calculation').click();
    assert.match(await page.locator('#detection-feedback').textContent(), /请先拍照取图/);
    await page.locator('#btn-history-records').click();
    await page.locator('#records-modal-loading').waitFor({state: 'hidden'});
    assert(await page.locator('#records-modal-overlay').isVisible());
    console.log('Live history:', await page.locator('#records-count').textContent(), await page.locator('#records-empty').textContent());
    const api = await page.evaluate(() => API.inspectionRecords);
    await page.keyboard.press('Escape');
    await page.route('**' + api + '*', route => route.fulfill({status: 503, json: {success: false, error: '测试服务异常'}}));
    await page.locator('#btn-history-records').click();
    await page.locator('#records-modal-loading').waitFor({state: 'hidden'});
    assert.match(await page.locator('#records-empty').textContent(), /加载失败.*测试服务异常/);
    await page.locator('#records-modal-close').click();
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=', 'base64');
    await page.route('**/test-history-original.png', route => route.fulfill({contentType: 'image/png', body: png}));
    await page.route('**' + api + '*', route => route.fulfill({json: {success: true, records: [
      {id: 1, created_at: '2026-11-15 10:00:00', position_index: 2, is_passed: true, score: 1, coverage_ratio: 1, original_image_url: '/test-history-original.png'},
      {id: 2, created_at: '2026-11-15 11:00:00', position_index: 3, is_passed: false, score: 0, coverage_ratio: 0, original_image_url: ''}
    ]}}));
    await page.locator('#btn-history-records').click();
    await page.locator('.record-card').first().waitFor();
    await page.locator('#records-filter-pass').selectOption('fail');
    assert.equal(await page.locator('.record-card').count(), 1);
    await page.locator('.record-card').click();
    assert.match(await page.locator('#records-modal-guidance').textContent(), /缺失/);
    await page.locator('#records-filter-pass').selectOption('all');
    await page.locator('#records-search').fill('POS2');
    assert.equal(await page.locator('.record-card').count(), 1);
    await page.locator('.record-card').click();
    await page.locator('#records-modal-overlay').waitFor({state: 'hidden'});
    assert(await page.locator('#preview-image').isVisible());
    assert.match(await page.locator('#pending-file-badge').textContent(), /POS2/);
    assert(await page.locator('#btn-save-detection-images').isDisabled());
    await page.locator('#pending-file-badge button').click();
    await page.locator('#file-upload-preview').setInputFiles({name: 'test.png', mimeType: 'image/png', buffer: png});
    await page.waitForFunction(() => document.querySelector('#pending-file-badge')?.textContent.includes('test.png'));
    await page.waitForFunction(() => foam2DRecipes.length > 0);
    await page.locator('#foam-recipe-select').selectOption(await page.evaluate(() => String(foam2DRecipes[0].id)));
    const uploadApi = await page.evaluate(() => API.uploadAndInspect);
    const requests = [];
    await page.route('**' + uploadApi, async route => {
      requests.push(route.request().postDataBuffer().toString());
      await route.fulfill({json: {success: false, error: '测试计算错误'}});
    });
    await page.locator('#btn-start-calculation').click();
    await page.waitForFunction(() => !calculationBusy);
    assert.equal(requests.length, 1);
    assert.match(requests[0], /filename="test.png"/);
    assert.match(requests[0], /name="recipe_id"/);
    assert.match(await page.locator('#detection-feedback').textContent(), /测试计算错误/);
    await page.evaluate(() => {pendingFile = null; lastCameraCaptureToken = 'test-preview-token';});
    await page.locator('#btn-start-calculation').click();
    await page.waitForFunction(() => !calculationBusy);
    assert.equal(requests.length, 2);
    assert.match(requests[1], /test-preview-token/);
    assert(await page.locator('#btn-start-calculation').isEnabled());
    await page.evaluate(() => {cal.dirty = true;});
    await page.locator('#btn-start-calculation').click();
    assert.match(await page.locator('#detection-feedback').textContent(), /ROI 已修改/);
    assert.equal(requests.length, 2);
    const chooserPromise = page.waitForEvent('filechooser');
    await page.locator('#btn-history-folder').click();
    await chooserPromise;
    assert.deepEqual(errors, []);
    console.log('PASS: history entry, errors, filters, missing image, import, clear, local upload, folder chooser; no page errors.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
