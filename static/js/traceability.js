/* ============================================================
   追溯页面 JavaScript - traceability.js
   ============================================================ */

(function () {
  'use strict';

  /* ---- 日期快捷按钮 ---- */
  const startInput = document.getElementById('tr-start-date');
  const endInput   = document.getElementById('tr-end-date');

  function fmtDate(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  document.querySelectorAll('[data-days]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const days = Number(btn.dataset.days);
      const today = new Date();
      const from = new Date();
      from.setDate(today.getDate() - Math.max(0, days - 1));

      if (startInput) startInput.value = fmtDate(from);
      if (endInput)   endInput.value   = fmtDate(today);

      document.querySelectorAll('[data-days]').forEach(function (b) {
        b.classList.toggle('selected', b === btn);
      });
    });
  });

  /* ---- 表格行展开详情 ---- */
  document.querySelectorAll('.tr-expandable').forEach(function (row) {
    row.addEventListener('click', function (e) {
      // 点击链接本身时不展开
      if (e.target.closest('a, button')) return;

      const detailId = row.dataset.detail;
      if (!detailId) return;
      const detail = document.getElementById(detailId);
      if (!detail) return;

      const isOpen = !detail.hidden;
      // 关闭同 table 内其他展开行
      const table = row.closest('table');
      if (table) {
        table.querySelectorAll('.tr-detail-row').forEach(function (dr) {
          dr.hidden = true;
        });
        table.querySelectorAll('.tr-expandable').forEach(function (r) {
          r.classList.remove('is-expanded');
        });
      }

      if (!isOpen) {
        detail.hidden = false;
        row.classList.add('is-expanded');
      }
    });
  });

})();
