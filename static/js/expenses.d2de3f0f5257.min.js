document.addEventListener('DOMContentLoaded', function () {
  "use strict";

  const style = document.createElement('style');
  style.textContent = `
    .dataTables_wrapper .dataTables_scrollBody{overflow-x:auto !important;overflow-y:hidden}
    table.table-sticky th:last-child,table.table-sticky td:last-child{
      position:sticky;right:0;background:var(--bs-body-bg,#fff);z-index:3;box-shadow:-4px 0 6px rgba(0,0,0,.06)
    }
  `;
  document.head.appendChild(style);

  const $one = (sel, ctx) => (ctx || document).querySelector(sel);
  const $all = (sel, ctx) => Array.from((ctx || document).querySelectorAll(sel));

  function setDisabled(el, disabled) {
    if (!el) return;
    const isSelect2 = el.classList && el.classList.contains('select2-hidden-accessible');
    el.disabled = !!disabled;
    if (isSelect2 && window.jQuery) jQuery(el).trigger('change.select2');
    if (disabled) el.setAttribute('disabled', 'disabled'); else el.removeAttribute('disabled');
  }

  function clearFieldValues(container) {
    if (!container) return;
    $all('input, select, textarea', container).forEach(inp => {
      if (inp.type === 'hidden') { inp.value = ''; return; }
      if (inp.tagName === 'SELECT') {
        inp.selectedIndex = -1;
        if (window.jQuery && jQuery.fn && jQuery.fn.select2) jQuery(inp).val(null).trigger('change');
      } else if ('value' in inp) {
        inp.value = '';
      }
    });
  }

  function textOfSelect(sel) {
    if (!sel) return '';
    if (sel.tagName === 'SELECT') {
      const opt = sel.selectedOptions && sel.selectedOptions[0];
      return (opt && (opt.textContent || opt.innerText || '').trim()) || '';
    }
    return (sel.value || '').trim();
  }

  const typeSel     = $one('#type_id');
  const amountInp   = $one('#amount');
  const amountHelp  = $one('#amountHelp');
  const paidToInp   = $one('#paid_to');
  const benInp      = $one('#beneficiary_name');

  const methodSel   = $one('#payment_method');
  const detailsWrap = $one('#methodDetails');

  const employeeFieldWrap = $one('#employee-field');
  const employeeSel = $one('#employee_id', employeeFieldWrap || document);

  const shipmentSel = $one('#shipment_id');
  const utilitySel  = $one('#utility_account_id');
  const stockAdjSel = $one('#stock_adjustment_id');

  const pStart = $one('#period_start');
  const pEnd   = $one('#period_end');

  function normalizeResults(data) {
    let items = [];
    if (Array.isArray(data)) items = data;
    else if (data && Array.isArray(data.results)) items = data.results;
    else if (data && Array.isArray(data.items)) items = data.items;
    return items.map(it => ({
      id: it.id ?? it.value ?? it.pk ?? it.ID,
      text: it.text ?? it.name ?? it.label ?? it.title ?? String(it.id ?? '')
    })).filter(x => x.id != null);
  }

  function prefillAjaxSelect(el) {
    const endpoint = el.dataset.endpoint || el.getAttribute('data-endpoint');
    if (!endpoint) return;
    const val = (el.value || '').trim();
    if (!val) return;
    const hasText = el.selectedOptions && el.selectedOptions[0] && el.selectedOptions[0].text && el.selectedOptions[0].text.trim();
    if (hasText) return;
    fetch(`${endpoint}?id=${encodeURIComponent(val)}`, { headers: { 'Accept': 'application/json' } })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        const items = normalizeResults(data || {});
        if (!items.length) return;
        const it = items[0];
        const opt = new Option(it.text, it.id, true, true);
        el.appendChild(opt);
        if (window.jQuery && jQuery.fn && jQuery.fn.select2) jQuery(el).trigger('change');
      })
      .catch(() => {});
  }

  function initAjaxSelect(el) {
    if (!(window.jQuery && $.fn && $.fn.select2) || !el) return;
    const $el = jQuery(el);
    if ($el.data('select2')) return;

    const endpoint = el.dataset.endpoint || el.getAttribute('data-endpoint');
    const placeholder = el.dataset.placeholder || el.getAttribute('data-placeholder') || 'اختر...';
    const minimumInputLength = parseInt(el.dataset.minlen || el.getAttribute('data-minlen') || '1', 10);

    const opt = {
      dir: 'rtl',
      width: '100%',
      allowClear: true,
      placeholder,
      language: {
        inputTooShort: () => `اكتب ${minimumInputLength} حرف على الأقل`,
        searching: () => 'جارِ البحث...',
        noResults: () => 'لا توجد نتائج'
      }
    };

    if (endpoint) {
      opt.ajax = {
        url: endpoint,
        dataType: 'json',
        delay: 250,
        cache: true,
        data: params => ({ q: params.term || '', page: params.page || 1 }),
        processResults: data => ({ results: normalizeResults(data) })
      };
      opt.minimumInputLength = minimumInputLength;
    }

    $el.select2(opt);
    prefillAjaxSelect(el);
  }

  function initAllAjaxSelects() {
    $all('.ajax-select').forEach(initAjaxSelect);
  }

  function resolveKind() {
    if (!typeSel) return 'MISC';
    const opt = typeSel.options[typeSel.selectedIndex] || {};
    const v   = (typeSel.value || '').toLowerCase();
    const t   = ((opt.text || '') + '').toLowerCase();
    const dataKind = (opt.dataset && (opt.dataset.kind || opt.getAttribute('data-kind'))) || '';

    if (dataKind) return (dataKind || '').toUpperCase();
    if (t.includes('راتب') || t.includes('رواتب') || t.includes('salary')) return 'SALARY';
    if (t.includes('جمرك') || t.includes('جمارك') || t.includes('custom')) return 'CUSTOMS';
    if (t.includes('كهرب') || t.includes('electr')) return 'ELECTRICITY';
    if (t.includes('مياه') || t.includes('ماء') || t.includes('water')) return 'WATER';
    if (t.includes('تالف') || t.includes('هدر') || t.includes('damag')) return 'DAMAGED';
    if (t.includes('استخدام') || t.includes('محل') || t.includes('داخلي') || t.includes('store')) return 'STORE_USE';
    if (v === 'salary') return 'SALARY';
    return 'MISC';
  }

  function toggleGroupsAndAmount() {
    const kind = resolveKind();

    if (employeeFieldWrap) {
      const show = (kind === 'SALARY');
      employeeFieldWrap.style.display = show ? '' : 'none';
      setDisabled(employeeSel, !show);
      if (!show) clearFieldValues(employeeFieldWrap);
    }

    const isStockBased = (kind === 'DAMAGED' || kind === 'STORE_USE' || (stockAdjSel && stockAdjSel.value));
    if (amountInp) {
      amountInp.readOnly = isStockBased;
      amountInp.classList.toggle('bg-light', isStockBased);
    }
    if (amountHelp) amountHelp.classList.toggle('d-none', !isStockBased);

    autoFillPaidTo();
  }

  function autoFillPaidTo() {
    if (!paidToInp) return;
    const kind = resolveKind();
    if (paidToInp.dataset.userEdited === '1') return;

    if (kind === 'SALARY' && employeeSel) {
      const name = textOfSelect(employeeSel);
      if (name) { paidToInp.value = name; paidToInp.dataset.autofill = 'employee'; return; }
    }
    if ((kind === 'ELECTRICITY' || kind === 'WATER') && utilitySel) {
      const util = textOfSelect(utilitySel);
      if (util) { paidToInp.value = util; paidToInp.dataset.autofill = 'utility'; return; }
    }
    if (kind === 'DAMAGED' || kind === 'STORE_USE') {
      paidToInp.value = 'تسوية مخزون'; paidToInp.dataset.autofill = 'stock'; return;
    }
    if (benInp && benInp.value.trim() !== '') {
      paidToInp.value = benInp.value.trim(); paidToInp.dataset.autofill = 'beneficiary'; return;
    }
  }

  if (paidToInp) {
    ['input','change'].forEach(evt => paidToInp.addEventListener(evt, () => {
      paidToInp.dataset.userEdited = (paidToInp.value.trim() ? '1' : '0');
    }));
  }
  if (benInp) ['input','change'].forEach(evt => benInp.addEventListener(evt, autoFillPaidTo));
  if (employeeSel) employeeSel.addEventListener('change', autoFillPaidTo);
  if (utilitySel)  utilitySel.addEventListener('change', autoFillPaidTo);

  const METHOD_FIELDS = {
    cash:   [],
    cheque: ['check_number', 'check_bank', 'check_due_date'],
    bank:   ['bank_transfer_ref'],
    card:   ['card_number', 'card_holder', 'card_expiry'],
    online: ['online_gateway', 'online_ref'],
    other:  []
  };

  function applyMethodDetails(method) {
    if (!detailsWrap) return;
    const need = new Set(METHOD_FIELDS[method] || []);
    let anyShown = false;

    $all('[data-field]', detailsWrap).forEach(box => {
      const fname = box.dataset.field || box.getAttribute('data-field');
      const show = need.has(fname);
      const inp = $one('input, select, textarea', box);
      box.style.display = show ? '' : 'none';
      setDisabled(inp, !show);
      if (!show && inp && 'value' in inp) inp.value = '';
      if (show) anyShown = true;
    });

    detailsWrap.style.display = anyShown ? '' : 'none';
  }

  if (methodSel) {
    applyMethodDetails((methodSel.value || '').toLowerCase());
    methodSel.addEventListener('change', () => applyMethodDetails((methodSel.value || '').toLowerCase()));
  }

  function validatePeriod() {
    if (!pStart || !pEnd) return true;
    if (!pStart.value || !pEnd.value) return true;
    const s = new Date(pStart.value);
    const e = new Date(pEnd.value);
    const ok = !(e < s);
    pStart.classList.toggle('is-invalid', !ok);
    pEnd.classList.toggle('is-invalid', !ok);
    return ok;
  }
  if (pStart) pStart.addEventListener('change', validatePeriod);
  if (pEnd)   pEnd.addEventListener('change', validatePeriod);

  async function tryPreviewStockAmount() {
    if (!stockAdjSel || !amountInp) return;
    const id = (stockAdjSel.value || '').trim();
    if (!id) return;

    const urlTpl = stockAdjSel.getAttribute('data-url-template');
    if (!urlTpl || !window.fetch) return;

    const url = urlTpl.replace('{id}', encodeURIComponent(id));
    try {
      const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      if (!res.ok) return;
      const data = await res.json();
      const total = (data && (data.total_cost ?? data.total ?? data.amount));
      if (typeof total === 'number' || (typeof total === 'string' && total !== '')) {
        amountInp.value = total;
      }
    } catch (_) {}
  }

  if (stockAdjSel) {
    stockAdjSel.addEventListener('change', () => {
      toggleGroupsAndAmount();
      tryPreviewStockAmount();
    });
  }

  if (typeSel) typeSel.addEventListener('change', toggleGroupsAndAmount);

  initAllAjaxSelects();
  toggleGroupsAndAmount();
  validatePeriod();
  if (stockAdjSel && stockAdjSel.value) tryPreviewStockAmount();

  const addStickyClass = id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('table-sticky');
  };
  ['expenses-table','types-table','employees-table'].forEach(addStickyClass);

  if (window.jQuery && $.fn && $.fn.DataTable) {
    const hasButtons = $.fn.dataTable && $.fn.dataTable.Buttons;
    const langUrl = "/static/datatables/Arabic.json";

    function initDT(tableEl, extraOpts) {
      if (!tableEl || $.fn.DataTable.isDataTable(tableEl)) return;
      const cols = tableEl.tHead ? tableEl.tHead.rows[0].cells.length : 0;
      const lastCol = cols ? cols - 1 : null;
      const baseOpts = {
        language: { url: langUrl },
        ordering: true,
        info: true,
        autoWidth: false,
        responsive: false,
        stateSave: true,
        pageLength: 25,
        scrollX: true,
        scrollCollapse: true,
        initComplete: function() {
          if (typeof window.onExpensesTableReady === "function") {
            window.onExpensesTableReady(this.api());
          }
        }
      };
      if (lastCol !== null) baseOpts.columnDefs = [{ orderable: false, targets: [lastCol], width: 180, className: 'text-nowrap' }];
      baseOpts.dom = hasButtons ? "Bfrtip" : "frtip";
      if (hasButtons) baseOpts.buttons = ["excelHtml5", "print"];
      const api = $(tableEl).DataTable(Object.assign({}, baseOpts, extraOpts || {}));
      $(window).on('resize', () => api.columns.adjust());
      document.addEventListener('shown.bs.tab', () => api.columns.adjust());
      document.addEventListener('shown.bs.collapse', () => api.columns.adjust());
    }

    initDT(document.getElementById('expenses-table'));
    initDT(document.getElementById('types-table'));
    initDT(document.getElementById('employees-table'));
  }

  window.ExpensesUI = {
    resolveKind,
    refreshUI: () => { initAllAjaxSelects(); toggleGroupsAndAmount(); }
  };
});
