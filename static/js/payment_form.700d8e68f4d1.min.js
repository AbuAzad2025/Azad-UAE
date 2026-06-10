document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  const filterSelectors = ['#filterEntity', '#filterStatus', '#filterDirection', '#filterMethod', '#startDate', '#endDate', '#filterCurrency'];
  const ENTITY_ENUM = { customer:'CUSTOMER', supplier:'SUPPLIER', partner:'PARTNER', sale:'SALE', service:'SERVICE', expense:'EXPENSE', loan:'LOAN', preorder:'PREORDER', shipment:'SHIPMENT' };
  const AR_STATUS = { COMPLETED:'مكتملة', PENDING:'قيد الانتظار', FAILED:'فاشلة', REFUNDED:'مُرجعة' };

  function inferEntityContext() {
    const path = location.pathname.replace(/\/+$/, '');
    const m = path.match(/^\/vendors\/(suppliers|partners)\/(\d+)\/payments$/i);
    if (m) return { entity_type: m[1].toLowerCase()==='suppliers' ? 'SUPPLIER' : 'PARTNER', entity_id: m[2] };
    const qs = new URLSearchParams(location.search);
    const et = (qs.get('entity_type') || '').toLowerCase();
    const ei = qs.get('entity_id') || '';
    return { entity_type: ENTITY_ENUM[et] || '', entity_id: ei || '' };
  }

  const ctx = inferEntityContext();
  const entSel = document.querySelector('#filterEntity');
  if (entSel && ctx.entity_type) { entSel.value = ctx.entity_type; entSel.disabled = true; }

  function injectStatementButtons() {
    if (!ctx.entity_type || !ctx.entity_id) return;
    const filtersRow = document.querySelector('.row.mb-4.g-2.align-items-end') || document.querySelector('.row.mb-4');
    if (!filtersRow || document.getElementById('btnExportCsv')) return;
    const wrap = document.createElement('div');
    wrap.className = 'col-auto d-flex gap-2';
    wrap.innerHTML = '<button id="btnPrint" class="btn btn-outline-secondary"><i class="fas fa-print me-1"></i> طباعة كشف</button><button id="btnExportCsv" class="btn btn-outline-success"><i class="fas fa-file-csv me-1"></i> تصدير CSV</button>';
    filtersRow.appendChild(wrap);
    document.getElementById('btnPrint').addEventListener('click', printStatement);
    document.getElementById('btnExportCsv').addEventListener('click', exportCsv);
  }
  injectStatementButtons();

  function debounce(fn, ms) { let t; return function () { clearTimeout(t); t = setTimeout(() => fn.apply(this, arguments), ms); }; }
  const debouncedReload = debounce(function () { updateUrlQuery(); loadPayments(1); }, 250);

  filterSelectors.forEach(function (sel) {
    const el = document.querySelector(sel);
    if (!el) return;
    el.addEventListener('change', debouncedReload, { passive: true });
    if (el.tagName === 'INPUT') el.addEventListener('input', debouncedReload, { passive: true });
  });

  function normalizeEntity(val) {
    if (!val) return '';
    const k = val.toString().toLowerCase();
    return ENTITY_ENUM[k] || val.toString().toUpperCase();
  }

  function normalizeMethod(v) {
    v = String(v || '').trim();
    if (!v) return '';
    return v.replace(/\s+/g,'_').replace(/-/g,'_').toUpperCase();
  }

  function normDir(v) {
    v = (v || '').toUpperCase();
    if (v === 'IN') return 'INCOMING';
    if (v === 'OUT') return 'OUTGOING';
    return v;
  }

  function validDates(start, end) {
    if (!start || !end) return { start, end };
    const s = new Date(start), e = new Date(end);
    if (isNaN(s) || isNaN(e)) return { start, end };
    if (s.getTime() > e.getTime()) return { start: end, end: start };
    return { start, end };
  }

  function currentFilters(page = 1) {
    const raw = {
      entity_type: normalizeEntity(document.querySelector('#filterEntity')?.value || ctx.entity_type || ''),
      status: document.querySelector('#filterStatus')?.value || '',
      direction: normDir(document.querySelector('#filterDirection')?.value || ''),
      method: normalizeMethod(document.querySelector('#filterMethod')?.value || ''),
      start_date: document.querySelector('#startDate')?.value || '',
      end_date: document.querySelector('#endDate')?.value || '',
      currency: (document.querySelector('#filterCurrency')?.value || '').toUpperCase(),
      page
    };
    const v = validDates(raw.start_date, raw.end_date);
    raw.start_date = v.start; raw.end_date = v.end;
    if (ctx.entity_id) raw.entity_id = ctx.entity_id;
    return raw;
  }

  function syncFiltersFromUrl() {
    const qs = new URLSearchParams(location.search);
    const setVal = (sel, v) => { const el = document.querySelector(sel); if (el && v != null) el.value = v; };
    setVal('#filterEntity', qs.get('entity_type'));
    setVal('#filterStatus', qs.get('status'));
    setVal('#filterDirection', qs.get('direction'));
    setVal('#filterMethod', qs.get('method'));
    setVal('#startDate', qs.get('start_date'));
    setVal('#endDate', qs.get('end_date'));
    setVal('#filterCurrency', qs.get('currency'));
  }

  function updateUrlQuery() {
    const raw = currentFilters();
    const params = new URLSearchParams();
    Object.entries(raw).forEach(function ([k, v]) { if (v && k !== 'page') params.append(k, v); });
    history.replaceState(null, '', location.pathname + (params.toString() ? ('?' + params.toString()) : ''));
  }

  let _abortCtrl = null;
  let _lastList = [];

  function loadPayments(page = 1) {
    const raw = currentFilters(page);
    const params = new URLSearchParams();
    Object.entries(raw).forEach(function ([k, v]) { if (v) params.append(k, v); });
    if (_abortCtrl) _abortCtrl.abort();
    _abortCtrl = new AbortController();
    setLoading(true);
    fetch('/payments/?' + params.toString(), { headers: { 'Accept': 'application/json' }, signal: _abortCtrl.signal })
      .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(function (data) {
        const list = Array.isArray(data.payments) ? data.payments : [];
        renderPaymentsTable(list);
        renderPagination(Number(data.total_pages || 1), Number(data.current_page || 1));
        renderTotals(data.totals || null);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        renderPaymentsTable([]);
        renderPagination(1, 1);
        renderTotals(null);
      })
      .finally(function () { setLoading(false); });
  }

  function setLoading(is) {
    const tbody = document.querySelector('#paymentsTable tbody');
    if (!tbody) return;
    if (is) tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-4"><div class="spinner-border spinner-border-sm me-2"></div>جارِ التحميل…</td></tr>';
  }

  function badgeForDirection(dir) {
    const v = String(dir || '').toUpperCase();
    return (v === 'IN' || v === 'INCOMING') ? '<span class="badge bg-success">وارد</span>' : '<span class="badge bg-danger">صادر</span>';
  }

  function badgeForStatus(st) {
    const s = String(st || '');
    const cls = s === 'COMPLETED' ? 'bg-success' : s === 'PENDING' ? 'bg-warning text-dark' : s === 'FAILED' ? 'bg-danger' : 'bg-secondary';
    const txt = AR_STATUS[s] || s || '';
    return '<span class="badge ' + cls + '">' + txt + '</span>';
  }

  function toNumber(s) {
    s = String(s || '')
      .replace(/[٠-٩]/g, d => '٠١٢٣٤٥٦٧٨٩'.indexOf(d))
      .replace(/[٬،\s]/g, '')
      .replace(',', '.');
    const n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  }

  function fmtAmount(v) { return toNumber(v).toFixed(2); }

  function deriveEntityLabel(p) {
    if (p.entity_display) return p.entity_display;
    const map = [
      ['customer_id', 'عميل'],
      ['supplier_id', 'مورد'],
      ['partner_id', 'شريك'],
      ['sale_id', 'بيع'],
      ['invoice_id', 'فاتورة'],
      ['service_id', 'صيانة'],
      ['shipment_id', 'شحنة'],
      ['expense_id', 'مصروف'],
      ['preorder_id', 'حجز'],
      ['loan_settlement_id', 'تسوية']
    ];
    for (const [key, label] of map) if (p[key]) return label + ' #' + p[key];
    return p.entity_type || '';
  }

  function renderPaymentsTable(list) {
    _lastList = list.slice();
    const tbody = document.querySelector('#paymentsTable tbody');
    tbody.innerHTML = '';
    if (!list.length) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td colspan="9" class="text-center text-muted py-4">لا توجد بيانات</td>';
      tbody.appendChild(tr);
      return;
    }
    let pageSum = 0;
    list.forEach(function (p) {
      const splitsHtml = (p.splits || []).map(function (s) {
        return '<span class="badge bg-secondary me-1">' + String((s.method || '')).toUpperCase() + ': ' + fmtAmount(s.amount) + ' ' + (p.currency || '') + '</span>';
      }).join(' ');
      const dateOnly = (p.payment_date || '').split('T')[0] || '';
      pageSum += toNumber(p.total_amount);
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + p.id + '</td>' +
        '<td>' + dateOnly + '</td>' +
        '<td>' + fmtAmount(p.total_amount) + '</td>' +
        '<td>' + (p.currency || '') + '</td>' +
        '<td>' + (splitsHtml || (p.method || '')) + '</td>' +
        '<td>' + badgeForDirection(p.direction) + '</td>' +
        '<td>' + badgeForStatus(p.status) + '</td>' +
        '<td>' + deriveEntityLabel(p) + '</td>' +
        '<td><a href="/payments/' + p.id + '" class="btn btn-info btn-sm">عرض</a></td>';
      tbody.appendChild(tr);
    });
    const t = document.createElement('tr');
    t.innerHTML = '<td></td><td class="text-end fw-bold">إجمالي الصفحة</td><td class="fw-bold">' + fmtAmount(pageSum) + '</td><td colspan="6"></td>';
    tbody.appendChild(t);
  }

  function renderPagination(totalPages, currentPage) {
    const ul = document.querySelector('#pagination');
    if (!ul) return;
    ul.innerHTML = '';
    totalPages = Math.max(1, totalPages || 1);
    currentPage = Math.min(Math.max(1, currentPage || 1), totalPages);

    function add(page, label, disabled, active, isEllipsis=false) {
      const li = document.createElement('li');
      li.className = 'page-item ' + (disabled ? 'disabled' : '') + ' ' + (active ? 'active' : '');
      li.innerHTML = '<a class="page-link" href="#" ' + (isEllipsis ? 'tabindex="-1" aria-disabled="true"' : 'data-page="' + page + '"') + '>' + label + '</a>';
      ul.appendChild(li);
    }

    add(currentPage - 1, 'السابق', currentPage <= 1, false);
    const windowSize = 2;
    const first = 1, last = totalPages;
    let start = Math.max(first, currentPage - windowSize);
    let end = Math.min(last, currentPage + windowSize);
    if (start > first) { add(first, '1', false, first === currentPage); if (start > first + 1) add(currentPage, '…', true, false, true); }
    for (let i = start; i <= end; i++) add(i, String(i), false, i === currentPage);
    if (end < last) { if (end < last - 1) add(currentPage, '…', true, false, true); add(last, String(last), false, last === currentPage); }
    add(currentPage + 1, 'التالي', currentPage >= totalPages, false);
    ul.querySelectorAll('.page-link[data-page]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        e.preventDefault();
        const page = parseInt(a.dataset.page, 10);
        if (!isNaN(page)) loadPayments(page);
      }, { passive: false });
    });
  }

  function renderTotals(totals) {
    const elIn = document.getElementById('totalIncoming');
    const elOut = document.getElementById('totalOutgoing');
    const elNet = document.getElementById('netTotal');
    const elAll = document.getElementById('grandTotal');
    if (!elIn && !elOut && !elNet && !elAll) return;
    const safe = totals || { total_incoming: 0, total_outgoing: 0, net_total: 0, grand_total: 0, total_paid: 0 };
    if (elIn) elIn.textContent = fmtAmount(safe.total_incoming || 0);
    if (elOut) elOut.textContent = fmtAmount(safe.total_outgoing || 0);
    if (elNet) elNet.textContent = fmtAmount(safe.net_total || 0);
    if (elAll) elAll.textContent = fmtAmount(safe.grand_total || 0);
  }

  function printStatement() {
    try {
      const table = document.getElementById('paymentsTable');
      const htmlTable = table.outerHTML;
      const title = 'كشف حساب - ' + (ctx.entity_type || '') + ' #' + (ctx.entity_id || '');
      const w = window.open('', 'stmt');
      w.document.write('<html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>' + title + '</title><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css"><style>body{padding:24px}h3{margin-bottom:16px}table{font-size:12px}</style></head><body><h3>' + title + '</h3>' + htmlTable + '<script>window.onload=function(){window.print();}</script></body></html>');
      w.document.close();
    } catch (e) {
      alert('تعذر الطباعة الآن.');
    }
  }

  function exportCsv() {
    try {
      const headers = Array.from(document.querySelectorAll('#paymentsTable thead th')).map(function (th) { return th.textContent.trim(); }).slice(0, 8);
      const rows = _lastList.map(function (p) {
        const dateOnly = (p.payment_date || '').split('T')[0] || '';
        const method = (p.splits && p.splits.length) ? p.splits.map(function (s) { return String((s.method || '')).toUpperCase() + ': ' + fmtAmount(s.amount); }).join(' | ') : (p.method || '');
        return [String(p.id || ''), dateOnly, fmtAmount(p.total_amount), String(p.currency || ''), method, (p.direction || ''), (AR_STATUS[p.status] || p.status || ''), String(deriveEntityLabel(p) || '')];
      });
      const csv = [headers].concat(rows).map(function (r) { return r.map(function (cell) { return '"' + String(cell).replace(/"/g, '""') + '"'; }).join(','); }).join('\n');
      const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const now = new Date();
      const ymd = '' + now.getFullYear() + String(now.getMonth() + 1).padStart(2, '0') + String(now.getDate()).padStart(2, '0');
      a.href = url;
      a.download = 'statement_' + (ctx.entity_type || 'ALL').toLowerCase() + '_' + (ctx.entity_id || 'all') + '_' + ymd + '.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert('تعذر إنشاء CSV.');
    }
  }

  syncFiltersFromUrl();
  updateUrlQuery();
  loadPayments();
  window.addEventListener('popstate', function () { syncFiltersFromUrl(); loadPayments(1); });
});

// وظائف البحث الذكي - محسنة للأداء
function initSmartSearch() {
  // البحث عن جميع حقول البحث في الحقول الديناميكية
  const searchInputs = document.querySelectorAll('input[placeholder*="اكتب"], input[placeholder*="البحث"]');

  searchInputs.forEach(input => {
    // تحديد نوع الجهة من الـ placeholder أو الـ name
    let entityType = 'customer'; // افتراضي

    if (input.placeholder.includes('مورد') || input.placeholder.includes('تاجر')) {
      entityType = 'supplier';
    } else if (input.placeholder.includes('شريك')) {
      entityType = 'partner';
    } else if (input.placeholder.includes('عميل')) {
      entityType = 'customer';
    }

    if (!entityType) return;

    // تجنب إضافة event listeners متعددة
    if (input.hasAttribute('data-smart-search-initialized')) return;
    input.setAttribute('data-smart-search-initialized', 'true');

    let searchTimeout;
    let currentResults = [];
    let selectedIndex = -1;

    // إنشاء قائمة النتائج مرة واحدة فقط
    let resultsList = input.parentNode.querySelector('.smart-search-results');
    if (!resultsList) {
      resultsList = document.createElement('div');
      resultsList.className = 'smart-search-results position-absolute w-100 bg-white border shadow-lg rounded';
      resultsList.style.display = 'none';
      resultsList.style.zIndex = '1000';
      resultsList.style.maxHeight = '300px';
      resultsList.style.overflowY = 'auto';

      input.parentNode.style.position = 'relative';
      input.parentNode.appendChild(resultsList);
    }

    // وظيفة البحث
    function performSearch(query) {
      // تم تغيير الشرط للسماح بالبحث بحرف واحد
      if (query.length < 1) { // Changed from 2 to 1
        hideResults();
        return;
      }

      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        fetch(`/payments/search-entities?type=${entityType}&q=${encodeURIComponent(query)}`)
          .then(response => response.json())
          .then(data => {
            currentResults = data;
            selectedIndex = -1;
            showResults(data);
          })
          .catch(error => {            hideResults();
          });
      }, 300);
    }

    // عرض النتائج
    function showResults(results) {
      if (results.length === 0) {
        hideResults();
        return;
      }
      resultsList.innerHTML = '';
      results.forEach((item, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = `smart-search-item p-2 border-bottom ${index === selectedIndex ? 'bg-light' : ''}`;
        itemDiv.innerHTML = `<span class="fw-bold">${item.name}</span> <small class="text-muted">(${item.id})</small>`;
        itemDiv.addEventListener('click', () => selectItem(item));
        resultsList.appendChild(itemDiv);
      });
      resultsList.style.display = 'block';
    }

    // إخفاء النتائج
    function hideResults() {
      resultsList.innerHTML = '';
      resultsList.style.display = 'none';
    }

    // تمييز العنصر المحدد
    function highlightSelectedItem() {
      resultsList.querySelectorAll('.smart-search-item').forEach((itemDiv, index) => {
        if (index === selectedIndex) {
          itemDiv.classList.add('bg-light');
          itemDiv.scrollIntoView({ block: 'nearest' });
        } else {
          itemDiv.classList.remove('bg-light');
        }
      });
    }

    // اختيار عنصر من القائمة
    function selectItem(item) {
      input.value = item.name;
      const hiddenInput = input.closest('[data-entity-type]').querySelector('input[type="hidden"]');
      if (hiddenInput) {
        hiddenInput.value = item.id;
      }
      hideResults();
    }

    // Event Listeners
    input.addEventListener('input', function() {
      performSearch(this.value.trim());
    });

    input.addEventListener('keydown', function(e) {
      if (resultsList.style.display === 'block' && currentResults.length > 0) {
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          selectedIndex = (selectedIndex + 1) % currentResults.length;
          highlightSelectedItem();
        } else if (e.key === 'ArrowUp') {
          e.preventDefault();
          selectedIndex = (selectedIndex - 1 + currentResults.length) % currentResults.length;
          highlightSelectedItem();
        } else if (e.key === 'Enter') {
          e.preventDefault();
          if (selectedIndex !== -1) {
            selectItem(currentResults[selectedIndex]);
          }
        }
      }
    });

    input.addEventListener('focus', function() {
      if (currentResults.length > 0 && resultsList.innerHTML !== '') {
        resultsList.style.display = 'block';
      }
    });

    input.addEventListener('blur', function() {
      setTimeout(() => {
        if (!resultsList.contains(document.activeElement)) {
          hideResults();
        }
      }, 100);
    });
  });
}

// استدعاء البحث الذكي تلقائياً عند تحميل الصفحة
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() {
    setTimeout(initSmartSearch, 500);
  });
} else {
  // DOM already loaded
  setTimeout(initSmartSearch, 100);
}

// استدعاء إضافي عند تحميل الصفحة بالكامل
window.addEventListener('load', function() {
  setTimeout(initSmartSearch, 200);
});