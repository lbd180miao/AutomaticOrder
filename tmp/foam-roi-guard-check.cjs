const assert = require('node:assert/strict');
let recipe = {}, currentStandardRoiReady = false, cal = {dirty: false}, feedback = [];
const currentDetectionRecipe = () => recipe;
const showDetectionFeedback = (...args) => feedback.push(args);
global.fetch = () => {throw new Error('ROI guard must not fetch images or teach templates');};
async function ensureStandardRoiForDetection() {
  const recipe = currentDetectionRecipe();
  if (cal.dirty) {
    showDetectionFeedback('ROI 已修改，请先保存到配方。', true);
    return false;
  }
  if (currentStandardRoiReady || recipe?.standard_roi_status?.ready || recipe?.standard_template_status?.ready) return true;
  showDetectionFeedback('请绘制有效的左右标准 ROI 并保存配方；无需建立图片模板。', true);
  return false;
}
(async () => {
  assert.equal(await ensureStandardRoiForDetection(), false);
  assert.match(feedback[0][0], /ROI/);
  recipe = {standard_roi_status: {ready: true}};
  assert.equal(await ensureStandardRoiForDetection(), true);
  cal.dirty = true;
  assert.equal(await ensureStandardRoiForDetection(), false);
  console.log('PASS: missing ROI blocks, saved ROI proceeds, unsaved changes block; no image requests.');
})().catch(error => {console.error(error); process.exitCode = 1;});
