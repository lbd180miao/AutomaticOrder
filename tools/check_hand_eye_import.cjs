const assert = require('node:assert/strict');
const {chromium} = require('C:/Users/11410/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs');
const sample = '-0.0274693, -0.9838417, -0.1769208, 32154.9957028, 0.9994231, -0.0234942, -0.0245244, 141163.6736290, 0.0199715, -0.1774924, 0.9839195, -6398.9009267, 0.0000000, 0.0000000, 0.0000000, 1.0000000';
(async () => {
  const browser = await chromium.launch({executablePath:'C:/Users/11410/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe',headless:true});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [], saves = [];
    page.on('pageerror', e=>errors.push(e.message));
    await page.route('**/api/hand-eye/calibrations/*/update/', async route=>{
      saves.push(route.request().postDataJSON());
      await route.fulfill({json:{success:true,data:{message:'test save'}}});
    });
    await page.goto(process.argv[2] || 'http://127.0.0.1:8082/vision/hand-eye/');
    await page.getByText('粘贴导入手眼矩阵',{exact:true}).click();
    await page.locator('#handEyeImportText').fill(sample);
    await page.locator('#importHandEyeButton').click();
    const read = id=>page.locator(`#${id} input`).evaluateAll(nodes=>nodes.map(n=>Number(n.value)));
    assert.deepEqual(await read('handEyeMatrix'), sample.split(',').map(Number));
    assert.equal(saves.length,0,'Import must not save automatically');
    await page.getByText('粘贴导入机器人位姿',{exact:true}).click();
    await page.locator('#robotPoseImportText').fill('256.564,1502.586,1281.666,-87.369,0.016,2.568');
    await page.locator('#importRobotPoseButton').click();
    const pose = await read('robotPoseMatrix');
    const expected = JSON.parse(fs.readFileSync('tmp/hand-eye-expected.json','utf8')).flat();
    expected.forEach((value,i)=>assert.ok(Math.abs(pose[i]-value)<1e-8,`matrix ${i}`));
    for(const text of ['1,2,3','1,2,,3,4,5,6','1,2,3,4,5,NaN','1,2,3,4,5,1e999']) {
      await page.locator('#robotPoseImportText').fill(text);
      await page.locator('#importRobotPoseButton').click();
      assert.ok(await page.locator('#robotPoseImportStatus').evaluate(n=>n.classList.contains('error')));
      assert.deepEqual(await read('robotPoseMatrix'),pose,'Invalid import changed draft');
    }
    await page.locator('#saveHandEyeButton').click();
    await page.waitForFunction(()=>document.querySelector('#handEyeBadge').textContent==='已保存');
    await page.locator('#saveRobotPoseButton').click();
    await page.waitForFunction(()=>document.querySelector('#robotPoseBadge').textContent==='已保存');
    assert.deepEqual(saves[0].T_flange_camera.matrix.flat(),sample.split(',').map(Number));
    assert.deepEqual(saves[1].T_base_flange.matrix.flat(),pose);
    assert.deepEqual(errors,[]);
    await page.screenshot({path:'tmp/hand-eye-import-verified.png'});
    console.log('PASS: both exact samples, SciPy-compatible pose, invalid inputs preserve draft, separate save payloads; no database writes.');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
