// 轻量交互：为带 data-confirm 的表单/按钮添加确认弹窗。
document.addEventListener('submit', function (event) {
  var form = event.target;
  var message = form.getAttribute('data-confirm');
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});
