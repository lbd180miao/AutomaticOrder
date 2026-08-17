// 轻量交互：为带 data-confirm 的表单/按钮添加确认弹窗。
document.addEventListener('submit', function (event) {
  var form = event.target;
  var message = form.getAttribute('data-confirm');
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});

// 操作台统一显示本机系统时间，避免每个业务页重复实现。
(function updateClock() {
  var clock = document.getElementById('system-clock');
  if (!clock) return;
  var now = new Date();
  clock.dateTime = now.toISOString();
  clock.textContent = now.toLocaleTimeString('zh-CN', {hour12: false});
  window.setTimeout(updateClock, 1000);
})();
