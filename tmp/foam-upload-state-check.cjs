const assert=require('node:assert/strict');
const elements=new Map();
const document={getElementById(id){if(!elements.has(id))elements.set(id,{style:{},classList:{remove(){}},removeAttribute(){}});return elements.get(id);}};
let lastDetectionResult={result_id:123}, recipeValidationCompleted=true;
const MAX_IMAGE_UPLOAD_BYTES=134217728;
function resetDetectionResult(title, message) {
  lastDetectionResult = null;
  recipeValidationCompleted = false;
  document.getElementById('btn-save-detection-images').disabled = true;
  document.getElementById('verdict-banner').className = 'verdict-banner idle';
  document.getElementById('verdict-icon').textContent = '—';
  document.getElementById('verdict-text').textContent = title;
  document.getElementById('verdict-sub').textContent = message;
  for (const key of ['present', 'aligned']) {
    document.getElementById(`card-${key}`).className = 'metric-card idle';
    document.getElementById(`value-${key}`).textContent = '无本次结果';
  }
  for (const id of ['detailed-result', 'detail-row', 'result-image']) document.getElementById(id).style.display = 'none';
  const image = document.getElementById('result-image');
  image.onload = image.onerror = null;
  image.removeAttribute('src');
  const placeholder = document.getElementById('result-placeholder');
  placeholder.textContent = message;
  placeholder.style.display = '';
  const state = document.getElementById('foam-recipe-save-state');
  state.textContent = title;
  state.classList.remove('saved');
}
function showDetectionFeedback(message, isError = false) {
  if (isError) {
    resetDetectionResult('本次操作未完成', '请处理错误后重新检测；上次结果不代表本次结果');
    document.getElementById('detection-timing').textContent = '已结束，未产生本次有效结果';
  }
  const feedback = document.getElementById('detection-feedback');
  feedback.hidden = !message;
  feedback.textContent = message;
  feedback.style.background = isError ? '#fff7ed' : '#eff6ff';
  feedback.style.color = isError ? '#9a3412' : '#1e40af';
}
function validateImageUpload(file) {
  if (file.size > MAX_IMAGE_UPLOAD_BYTES) {
    throw new Error(`图片大小 ${(file.size / 1048576).toFixed(1)} MB，超过上限 ${MAX_IMAGE_UPLOAD_BYTES / 1048576} MB`);
  }
}
showDetectionFeedback('检测失败',true);
assert.equal(lastDetectionResult,null);
assert.equal(recipeValidationCompleted,false);
assert.equal(document.getElementById('detailed-result').style.display,'none');
assert.equal(document.getElementById('btn-save-detection-images').disabled,true);
assert.match(document.getElementById('detection-timing').textContent,/已结束/);
validateImageUpload({size:60*1048576});
assert.throws(()=>validateImageUpload({size:129*1048576}),/128 MB/);
console.log('PASS: upload checks and stale result/timing reset');
