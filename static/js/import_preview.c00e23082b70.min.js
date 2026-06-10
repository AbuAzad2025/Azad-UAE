(function () {
  const rows = window.__IMPORT_ROWS__ || [];
  const table = document.getElementById('previewTable');
  const extra = document.getElementById('extraTable');
  const searchBox = document.getElementById('searchBox');
  const filter = document.getElementById('quickFilter');
  const btnSave = document.getElementById('btnSave');
  const btnCommit = document.getElementById('btnCommit');
  const saveField = document.getElementById('rows_json_save');
  const commitField = document.getElementById('rows_json_commit');
  const token = document.getElementById('token')?.value || '';
  const btnCompact = document.getElementById('btnToggleCompact');

  // Notification system (basic)
  function notify(message, type = 'info') {
    const existing = document.getElementById('notifyBox');
    if (existing) existing.remove();

    const box = document.createElement('div');
    box.id = 'notifyBox';
    box.className = `alert alert-${type} shadow-sm position-fixed top-0 end-0 m-3`;
    box.style.zIndex = 2000;
    box.innerHTML = message;

    document.body.appendChild(box);
    setTimeout(() => box.remove(), 4000);
  }

  // Counter display
  let resultCount = document.getElementById('resultCount');
  if (!resultCount) {
    resultCount = document.createElement('div');
    resultCount.id = 'resultCount';
    resultCount.className = 'mt-2 text-muted small';
    table.parentElement.appendChild(resultCount);
  }

  function updateResultCount() {
    const totalRows = table.tBodies[0].rows.length;
    const visibleRows = Array.from(table.tBodies[0].rows).filter(tr => tr.style.display !== 'none').length;
    resultCount.textContent = `عدد الصفوف الظاهرة: ${visibleRows} من ${totalRows}`;
  }

  function collect() {
    const inputMap = {};

    const extractInputs = (tbody) => {
      Array.from(tbody.rows).forEach(row => {
        const rowIndex = parseInt(row.getAttribute('data-rownum'), 10);
        if (!inputMap[rowIndex]) inputMap[rowIndex] = {};

        row.querySelectorAll('.cell').forEach(input => {
          const field = input.getAttribute('data-field');
          const value = input.value;
          inputMap[rowIndex][field] = value;
        });
      });
    };

    extractInputs(table.tBodies[0]);
    extractInputs(extra.tBodies[0]);

    return rows.map(row => {
      const index = row.rownum;
      const combinedData = Object.assign({}, row.data || {}, inputMap[index] || {});
      return {
        rownum: index,
        data: combinedData,
        match: row.match || {},
        soft_warnings: row.soft_warnings || []
      };
    });
  }

  function applyFilters() {
    const query = (searchBox?.value || '').trim().toLowerCase();
    const mode = filter?.value || '';
    const body = table.tBodies[0];

    let shown = 0;

    Array.from(body.rows).forEach(tr => {
      const rowNum = tr.getAttribute('data-rownum');
      const extraRow = extra.querySelector(`tr[data-rownum="${rowNum}"]`);
      const rowText = Array.from(tr.querySelectorAll('input')).map(i => i.value.toLowerCase()).join(' ');

      const matchesSearch = !query || rowText.includes(query);
      let matchesFilter = true;

      if (mode === 'missing') matchesFilter = tr.classList.contains('row-missing');
      else if (mode === 'warnings') matchesFilter = tr.classList.contains('row-warning');
      else if (mode === 'new') matchesFilter = tr.classList.contains('row-new');
      else if (mode === 'matched') matchesFilter = tr.classList.contains('row-matched');

      const shouldShow = matchesSearch && matchesFilter;
      tr.style.display = shouldShow ? '' : 'none';
      if (extraRow) extraRow.style.display = shouldShow ? '' : 'none';

      if (shouldShow) shown++;
    });

    updateResultCount();
  }

  function validateInline() {
    let missingCount = 0;
    Array.from(table.tBodies[0].rows).forEach(tr => {
      const nameInput = tr.querySelector('input[data-field="name"]');
      const isMissing = nameInput && !nameInput.value.trim();
      tr.classList.toggle('row-missing', isMissing);
      if (isMissing) missingCount++;
    });

    if (missingCount > 0) {
      notify(`⚠️ يوجد ${missingCount} صف بدون اسم.`, 'warning');
    }
  }

  function prepare(targetField) {
    const data = collect();
    const json = JSON.stringify({ normalized: data });
    if (targetField) targetField.value = json;
  }

  // Bind events
  if (searchBox) searchBox.addEventListener('input', applyFilters);
  if (filter) filter.addEventListener('change', applyFilters);
  if (btnCompact) btnCompact.addEventListener('click', () => {
    document.body.classList.toggle('compact');
  });

  if (btnSave) {
    btnSave.addEventListener('click', () => {
      validateInline();
      prepare(saveField);
      notify('✅ تم تجهيز البيانات للحفظ', 'success');
      document.getElementById('saveForm').submit();
    });
  }

  if (btnCommit) {
    btnCommit.addEventListener('click', () => {
      validateInline();
      prepare(commitField);
      notify('✅ تم تجهيز البيانات للإدخال النهائي', 'success');
      document.getElementById('commitForm').submit();
    });
  }

  // Initial
  validateInline();
  applyFilters();
})();
