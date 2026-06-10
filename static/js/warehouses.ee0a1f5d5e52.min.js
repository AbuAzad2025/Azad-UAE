(function () {
  if (window.__WAREHOUSES_INIT__) return;
  window.__WAREHOUSES_INIT__ = true;

  function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var input = document.querySelector('input[name="csrf_token"]');
    if (input && input.value) return input.value;
    var m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function showNotification(message, type) {
    type = type || 'info';
    var c = document.getElementById('notification-container');
    if (!c) {
      c = document.createElement('div');
      c.id = 'notification-container';
      c.style.position = 'fixed';
      c.style.top = '20px';
      c.style.right = '20px';
      c.style.zIndex = '2000';
      document.body.appendChild(c);
    }
    var el = document.createElement('div');
    el.className = 'alert alert-' + type + ' alert-dismissible fade show shadow-sm mb-2';
    el.setAttribute('role', 'alert');
    var isBS5 = !!(window.bootstrap && window.bootstrap.Modal);
    var closeBtn = isBS5
      ? '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>'
      : '<button type="button" class="close" data-dismiss="alert" aria-label="Close"><span aria-hidden="true">&times;</span></button>';
    el.innerHTML = message + closeBtn;
    c.appendChild(el);
    setTimeout(function () {
      if (!el.parentNode) return;
      el.classList.remove('show');
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 300);
    }, 5000);
  }
  window.showNotification = showNotification;

  function postJSON(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCSRFToken() || ''
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload || {})
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var msg = (data && (data.error || data.message)) || ('HTTP ' + res.status);
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function postForm(url, formElem) {
    var fd = new FormData(formElem);
    var csrf = getCSRFToken();
    if (csrf && !fd.get('csrf_token')) fd.append('csrf_token', csrf);
    return fetch(url, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
      body: fd
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok && !data.success) {
          var msg = (data && (data.error || data.message)) || ('HTTP ' + res.status);
          throw new Error(msg);
        }
        return data;
      });
    });
  }

  function appendAndSelectOption(selectEl, id, text) {
    if (!selectEl || !id) return;
    var opt = new Option(text, id, true, true);
    selectEl.add(opt);
    if (window.jQuery) jQuery(selectEl).trigger('change');
  }

  function markRequired(container) {
    var root = container || document;
    var nodes = root.querySelectorAll('[required]');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      el.setAttribute('aria-required', 'true');
      var id = el.id;
      var label = id ? root.querySelector('label[for="' + id + '"]') : null;
      if (!label) {
        var grp = el.closest('.form-group');
        if (grp) label = grp.querySelector('label');
      }
      if (label && !label.querySelector('.req')) {
        var s = document.createElement('span');
        s.className = 'req';
        s.textContent = '*';
        label.appendChild(s);
      }
      if (el.classList.contains('select2') || (el.tagName === 'SELECT' && el.classList.contains('select2'))) {
        var wrap = el.closest('.form-group') || el.parentElement || el;
        if (wrap) wrap.classList.add('is-required');
      }
    }
  }

  function toNumber(v) {
    if (v == null) return null;
    var s = String(v)
      .replace(/[^\d٠-٩.,-]/g, '')
      .replace(/[٠-٩]/g, function (d) { return '٠١٢٣٤٥٦٧٨٩'.indexOf(d); })
      .replace(/,/g, '.')
      .trim();
    if (s === '' || s === '-' || s === '.' || s === '-.') return null;
    var n = Number(s);
    return isFinite(n) ? n : null;
  }

  function prefetchOnce($el, endpoint) {
    if (!$el || !endpoint) return;
    if ($el.data('prefetched')) return;
    $el.data('prefetched', true);
    fetch(endpoint + (endpoint.indexOf('?') >= 0 ? '&' : '?') + 'q=&limit=20', {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var arr = Array.isArray(data) ? data : (data.results || data.data || []);
      (arr || []).forEach(function (x) {
        var id = x.id;
        var text = x.text || x.name || String(id);
        if (!id) return;
        if ($el.find('option[value="' + id + '"]').length === 0) {
          var opt = new Option(text, id, false, false);
          $el.append(opt);
        }
      });
      $el.trigger('change.select2');
    })
    .catch(function () {});
  }

  function initSelect2(root) {
    if (!(window.jQuery && jQuery.fn.select2)) return;
    var $root = jQuery(root || document);
    $root.find('select.select2').each(function () {
      var $el = jQuery(this);
      if ($el.data('select2')) return;
      var endpoint = $el.data('url') || $el.data('endpoint');
      var placeholder = $el.attr('placeholder') || 'اختر...';
      var opts = {
        width: '100%',
        dir: 'rtl',
        theme: 'bootstrap4',
        allowClear: true,
        placeholder: placeholder,
        minimumInputLength: 0
      };
      if (endpoint) {
        opts.ajax = {
          delay: 250,
          cache: true,
          url: endpoint,
          dataType: 'json',
          data: function (params) {
            return { q: (params && params.term) ? params.term : '', limit: 20 };
          },
          processResults: function (data) {
            var arr = Array.isArray(data) ? data : (data.results || data.data || []);
            return {
              results: (arr || []).map(function (x) {
                return { id: x.id, text: x.text || x.name || String(x.id) };
              })
            };
          }
        };
      }
      $el.select2(opts);
      if (endpoint) prefetchOnce($el, endpoint);
    });
  }

  function initTransferInline() {
    var form = document.querySelector('form#transfer-inline-form, form[data-transfer-form]');
    if (!form || form.__boundTransferInline) return;
    form.__boundTransferInline = true;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('button[type="submit"], .btn-primary');
      if (btn) btn.disabled = true;
      var pid = form.querySelector('[name="product_id"]')?.value;
      var sid = form.querySelector('[name="source_id"]')?.value;
      var did = form.querySelector('[name="destination_id"]')?.value;
      var qty = form.querySelector('[name="quantity"]')?.value;
      var date = form.querySelector('[name="date"]')?.value || '';
      var notes = form.querySelector('[name="notes"]')?.value || '';
      var endpoint = '/warehouses/' + (sid || '').toString().trim() + '/transfer';
      if (!pid || !sid || !did || !qty || sid === did) {
        showNotification('تحقق من المدخلات: اختر الصنف، المصدر، الوجهة، والكمية أكبر من صفر.', 'warning');
        if (btn) btn.disabled = false;
        return;
      }
      postJSON(endpoint, {
        product_id: Number(pid),
        source_id: Number(sid),
        destination_id: Number(did),
        quantity: Number(qty),
        date: date,
        notes: notes
      })
      .then(function (res) {
        showNotification('تم تنفيذ التحويل بنجاح. الرصيد بعد العملية - المصدر: ' + res.source_onhand + ' | الوجهة: ' + res.destination_onhand, 'success');
        form.reset();
      })
      .catch(function (err) {
        var m = (err && err.message) || 'خطأ غير معروف';
        if (/insufficient_stock/i.test(m)) m = 'لا توجد كمية كافية في المستودع المصدر.';
        if (/mismatch/i.test(m)) m = 'معرف المستودع لا يطابق المصدر.';
        if (/invalid/i.test(m)) m = 'بيانات غير صالحة.';
        showNotification(m, 'danger');
      })
      .finally(function () { if (btn) btn.disabled = false; });
    });
  }

  function initExchangeInline() {
    var form = document.querySelector('form#exchange-inline-form, form[data-exchange-form]');
    if (!form || form.__boundExchangeInline) return;
    form.__boundExchangeInline = true;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('button[type="submit"], .btn-primary');
      if (btn) btn.disabled = true;
      var wid = form.getAttribute('data-warehouse-id') || form.querySelector('[name="warehouse_id"]')?.value;
      var pid = form.querySelector('[name="product_id"]')?.value;
      var qty = form.querySelector('[name="quantity"]')?.value;
      var dir = (form.querySelector('[name="direction"]')?.value || '').toUpperCase();
      var unit_cost = form.querySelector('[name="unit_cost"]')?.value;
      var partner_id = form.querySelector('[name="partner_id"]')?.value || null;
      var notes = form.querySelector('[name="notes"]')?.value || '';
      var endpoint = '/warehouses/' + (wid || '').toString().trim() + '/exchange';
      if (!wid || !pid || !qty || !dir) {
        showNotification('تحقق من المدخلات: اختر الصنف والاتجاه والكمية.', 'warning');
        if (btn) btn.disabled = false;
        return;
      }
      postJSON(endpoint, {
        product_id: Number(pid),
        quantity: Number(qty),
        direction: dir,
        unit_cost: unit_cost === '' ? null : Number(unit_cost),
        partner_id: partner_id ? Number(partner_id) : null,
        notes: notes
      })
      .then(function (res) {
        showNotification('تم تسجيل الحركة. الكمية الجديدة: ' + res.new_quantity, 'success');
        form.reset();
      })
      .catch(function (err) {
        var m = (err && err.message) || 'خطأ غير معروف';
        if (/insufficient_stock/i.test(m)) m = 'لا توجد كمية كافية لهذه الحركة.';
        if (/invalid/i.test(m)) m = 'بيانات غير صالحة.';
        showNotification(m, 'danger');
      })
      .finally(function () { if (btn) btn.disabled = false; });
    });
  }

  function bindTransferForm(selector) {
    var form = document.querySelector(selector);
    if (!form || form.__boundTransferForm) return;
    form.__boundTransferForm = true;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      postForm(form.action || window.location.href, form)
        .then(function (res) {
          if (res && (res.ok === true || res.success === true)) {
            showNotification(res.message || 'تم تحويل الكمية بنجاح.', 'success');
            if (res.redirect) { window.location = res.redirect; return; }
          } else {
            var msg = (res && (res.message || res.error)) || 'تعذر تنفيذ التحويل';
            showNotification(msg, 'danger');
          }
        })
        .catch(function (err) {
          showNotification((err && err.message) || 'خطأ غير متوقع', 'danger');
        });
    });
  }

  function bindExchangeForm(selector) {
    var form = document.querySelector(selector);
    if (!form || form.__boundExchangeForm) return;
    form.__boundExchangeForm = true;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      postForm(form.action || window.location.href, form)
        .then(function (res) {
          if (res && (res.ok === true || res.success === true)) {
            var msg = 'تم تسجيل العملية.' + (typeof res.new_quantity !== 'undefined' ? (' الكمية الجديدة: ' + res.new_quantity) : '');
            showNotification(msg, 'success');
            if (res.redirect) { window.location = res.redirect; return; }
          } else {
            var msg2 = (res && (res.message || res.error)) || 'تعذر تنفيذ العملية';
            showNotification(msg2, 'danger');
          }
        })
        .catch(function (err) {
          showNotification((err && err.message) || 'خطأ غير متوقع', 'danger');
        });
    });
  }

  function bindStockForms() {
    if (!(window.jQuery)) return;
    jQuery('form.stock-level-form').each(function () {
      var form = this;
      if (form.__boundStockForm) return;
      form.__boundStockForm = true;
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        postForm(form.action || window.location.href, form)
          .then(function (resp) {
            var ok = resp && (resp.success === true || resp.ok === true);
            if (!ok) {
              var m = (resp && (resp.alert || resp.error || resp.message)) || 'تعذر إتمام العملية.';
              showNotification(m, 'warning');
              return;
            }
            if (typeof resp.quantity !== 'undefined') {
              showNotification('تم تحديث المخزون. الكمية الحالية: ' + resp.quantity, 'success');
            } else {
              showNotification('تم التنفيذ بنجاح.', 'success');
            }
            setTimeout(function(){ location.reload(); }, 600);
          })
          .catch(function (err) {
            showNotification((err && err.message) || 'خطأ غير متوقع', 'danger');
          });
      });
    });
  }

  function wireQuickPicker() {
    var $ = window.jQuery;
    if (!$) return;
    var $quick = $('#product-quick');
    if (!$quick.length || $quick.data('wiredQuick')) return;
    $quick.data('wiredQuick', true);
    $quick.on('select2:select', function (e) {
      var id = e.params && e.params.data && e.params.data.id;
      var text = e.params && e.params.data && (e.params.data.text || '');
      if (!id) return;
      ['#stock-product', '#transfer-product', '#exchange-product'].forEach(function (sel) {
        var $s = $(sel);
        if ($s.length) {
          var opt = new Option(text, id, true, true);
          $s.append(opt).trigger('change');
        }
      });
    });
  }

  function wireBarcodePick() {
    var input = document.getElementById('barcode-input');
    if (!input || input.__wiredBarcode) return;
    input.__wiredBarcode = true;
    input.addEventListener('keypress', function (ev) {
      if (ev.which === 13) {
        ev.preventDefault();
        var code = (input.value || '').trim();
        if (!code) return;
        var $quick = window.jQuery && jQuery('#product-quick');
        if (!$quick || !$quick.length) return;
        var ep = $quick.data('endpoint') || $quick.data('url');
        if (!ep) return;
        fetch(ep + '?q=' + encodeURIComponent(code) + '&limit=1', {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin'
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var r = (data.results || data.data || [])[0];
          if (!r) { showNotification('لم يتم العثور على منتج مطابق.', 'warning'); return; }
          var id = r.id, text = r.text || r.name || '';
          ['#product-quick','#stock-product','#transfer-product','#exchange-product'].forEach(function (sel) {
            var $s = jQuery(sel);
            if ($s.length) {
              $s.append(new Option(text, id, true, true)).trigger('change');
            }
          });
          showNotification('تم اختيار المنتج: ' + text, 'info');
        })
        .catch(function () { showNotification('فشل البحث عن المنتج.', 'danger'); });
      }
    });
  }

  function initShipmentsTable() {
    if (!(window.jQuery && jQuery.fn.DataTable)) return;
    var $tbl = jQuery('#shipments-table');
    if (!$tbl.length) return;
    if (jQuery.fn.DataTable.isDataTable($tbl)) return;
    $tbl.DataTable({
      pageLength: 10,
      order: [[2, 'desc']],
      language: { url: '/static/datatables/Arabic.json' }
    });
  }

  function setDefaultSourceIfPossible() {
    var wid = null, wname = null;
    var exForm = document.getElementById('exchange-form');
    if (exForm) {
      var hid = exForm.querySelector('input[name="warehouse_id"]');
      if (hid && hid.value) wid = hid.value;
      wname = exForm.getAttribute('data-warehouse-name') || null;
    }
    if (!wid) {
      var metaWid = document.querySelector('meta[name="current-warehouse-id"]');
      if (metaWid && metaWid.content) wid = metaWid.content;
      var metaWname = document.querySelector('meta[name="current-warehouse-name"]');
      if (metaWname && metaWname.content) wname = metaWname.content;
    }
    var src = document.getElementById('transfer-source');
    if (src && wid) {
      appendAndSelectOption(src, wid, wname || ('#' + wid));
    }
  }

  function initInventoryDataTable(){
    if (!(window.jQuery && jQuery.fn.DataTable)) return;
    var $tbl = jQuery('#inventory-table');
    if (!$tbl.length || jQuery.fn.DataTable.isDataTable($tbl)) return;
    $tbl.DataTable({
      pageLength: 50,
      order: [[3, 'asc']],
      scrollX: true,
      language: { url: '/static/datatables/Arabic.json' }
    });
  }

  function initExpandedToggle(){
    var table = document.getElementById('inventory-table');
    var btn   = document.getElementById('btnToggleExpanded');
    if (!table || !btn || btn.__wired) return;
    btn.__wired = true;
    var KEY = 'inv_preview_expanded';
    function apply(on){
      table.classList.toggle('expanded-on', !!on);
      if (window.jQuery && jQuery.fn.DataTable && jQuery.fn.DataTable.isDataTable('#inventory-table')){
        jQuery('#inventory-table').DataTable().columns.adjust().draw(false);
      }
      btn.textContent = on ? 'نسخة مصغرة' : 'نسخة موسعة';
    }
    apply(localStorage.getItem(KEY) === '1');
    btn.addEventListener('click', function(){
      var on = !table.classList.contains('expanded-on');
      localStorage.setItem(KEY, on ? '1' : '0');
      apply(on);
    });
    document.addEventListener('keydown', function(e){
      if (e.key && e.key.toLowerCase() === 'x' && document.activeElement && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA'){
        e.preventDefault();
        btn.click();
      }
    });
  }

  function validatePartnerSection() {
    var ok = true;
    var container = document.getElementById('partners-container');
    if (!container) return true;
    var rows = Array.prototype.slice.call(container.querySelectorAll('.partner-entry'));
    var validRows = [];
    rows.forEach(function (row) {
      var pid  = row.querySelector('select[name="partner_id"]');
      var perc = row.querySelector('input[name="share_percentage"]');
      var amt  = row.querySelector('input[name="share_amount"]');
      var pidVal  = pid && pid.value ? String(pid.value).trim() : '';
      var percVal = toNumber(perc && perc.value);
      var amtVal  = toNumber(amt && amt.value);
      row.classList.remove('is-invalid');
      if (pidVal && ((percVal && percVal > 0) || (amtVal && amtVal > 0))) {
        validRows.push({ perc: percVal || 0, amt: amtVal || 0, row: row });
      }
    });
    if (!validRows.length) {
      ok = false;
      showNotification('أضف شريكًا واحدًا على الأقل مع نسبة أو قيمة مساهمة.', 'warning');
      var btn = document.getElementById('add-partner-btn');
      if (btn) btn.focus();
    } else {
      var allPercOnly = validRows.every(function (r) { return r.perc > 0 && (!r.amt || r.amt === 0); });
      if (allPercOnly) {
        var total = validRows.reduce(function (s, r) { return s + r.perc; }, 0);
        if (total > 100.0001) {
          ok = false;
          showNotification('مجموع نسب الشركاء يتجاوز 100٪.', 'danger');
          validRows.forEach(function (r) { r.row.classList.add('is-invalid'); });
        }
      }
    }
    return ok;
  }

  function validateExchangeSection() {
    var container = document.getElementById('vendors-container');
    if (!container) return true;
    var rows = Array.prototype.slice.call(container.querySelectorAll('.vendor-entry'));
    var hasSupplier = rows.some(function (row) {
      var sid = row.querySelector('select[name="supplier_id"]');
      return sid && sid.value && String(sid.value).trim() !== '';
    });
    if (!hasSupplier) {
      showNotification('أضف مورّدًا واحدًا على الأقل لمستودع التبادل.', 'warning');
      var btn = document.getElementById('add-vendor-btn');
      if (btn) btn.focus();
      return false;
    }
    return true;
  }

  function toggleSectionsByType(wtype) {
    var partnerSection = document.getElementById('partner-section');
    var exchangeSection = document.getElementById('exchange-section');
    if (partnerSection) partnerSection.classList.toggle('d-none', wtype !== 'PARTNER');
    if (exchangeSection) exchangeSection.classList.toggle('d-none', wtype !== 'EXCHANGE');
  }

  function initPage() {
    markRequired(document);
    initSelect2(document);
    initTransferInline();
    initExchangeInline();
    var form = document.getElementById('add-product-form');
    var wtype = (form && form.dataset && form.dataset.wtype ? form.dataset.wtype : '').toUpperCase();
    var isExchangeEl = document.getElementById('is_exchange_id');
    toggleSectionsByType(wtype);
    if (isExchangeEl) {
      if (wtype === 'EXCHANGE') isExchangeEl.checked = true;
      var exchangeSection = document.getElementById('exchange-section');
      if (exchangeSection) {
        exchangeSection.classList.toggle('d-none', !(isExchangeEl.checked || wtype === 'EXCHANGE'));
        isExchangeEl.addEventListener('change', function () {
          exchangeSection.classList.toggle('d-none', !isExchangeEl.checked);
        });
      }
    }
    var partnersContainer = document.getElementById('partners-container');
    var addPartnerBtn = document.getElementById('add-partner-btn');
    var partnerTpl = document.getElementById('partner-template');
    if (addPartnerBtn && partnersContainer && partnerTpl && partnerTpl.content) {
      addPartnerBtn.addEventListener('click', function () {
        var node = document.importNode(partnerTpl.content, true);
        partnersContainer.appendChild(node);
        initSelect2(partnersContainer);
        markRequired(partnersContainer);
      });
      partnersContainer.addEventListener('click', function (e) {
        var rm = e.target.closest('.remove-partner-btn');
        if (rm) { var row = e.target.closest('.partner-entry'); if (row) row.remove(); }
      });
    }
    var vendorsContainer = document.getElementById('vendors-container');
    var addVendorBtn = document.getElementById('add-vendor-btn');
    var vendorTpl = document.getElementById('vendor-template');
    if (addVendorBtn && vendorsContainer && vendorTpl && vendorTpl.content) {
      addVendorBtn.addEventListener('click', function () {
        var node = document.importNode(vendorTpl.content, true);
        vendorsContainer.appendChild(node);
        initSelect2(vendorsContainer);
        markRequired(vendorsContainer);
      });
      vendorsContainer.addEventListener('click', function (e) {
        var rm = e.target.closest('.remove-vendor-btn');
        if (rm) { var row = e.target.closest('.vendor-entry'); if (row) row.remove(); }
      });
    }
    var lastSupplierSelect = null;
    document.addEventListener('focusin', function (e) {
      if (e.target && e.target.matches('#vendors-container select[name="supplier_id"]')) {
        lastSupplierSelect = e.target;
      }
    });
    window.lastSupplierSelect = lastSupplierSelect;
    (function initCategoryModal() {
      var mform = document.getElementById('create-category-form');
      var select = document.getElementById('category_id');
      if (!mform || !select) return;
      mform.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = mform.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var name = (mform.querySelector('input[name="name"]') || {}).value || '';
        name = name.trim();
        var notesEl = mform.querySelector('textarea[name="notes"]');
        var notes = notesEl ? (notesEl.value || '').trim() : '';
        if (!name) { showNotification('أدخل اسم الفئة', 'warning'); if (btn) btn.disabled = false; return; }
        var url = mform.getAttribute('data-url') || mform.action || window.location.href;
        postJSON(url, { name: name, notes: notes })
          .then(function (data) {
            var item = data.id ? { id: data.id, text: data.name || name }
                               : ((data.results && data.results[0]) ? data.results[0] : null);
            if (!item) throw new Error('استجابة غير متوقعة من الخادم');
            appendAndSelectOption(select, item.id, item.text || name);
            showNotification('تمت إضافة الفئة.', 'success');
            if (window.jQuery) jQuery(mform).closest('.modal').modal('hide');
            mform.reset();
          })
          .catch(function (err) {
            showNotification('تعذر إضافة الفئة: ' + (err && err.message ? err.message : 'خطأ غير معروف'), 'danger');
          })
          .finally(function () { if (btn) btn.disabled = false; });
      });
    })();
    (function initEquipmentTypeModal() {
      var mform = document.getElementById('equipmentTypeForm');
      var select = document.getElementById('vehicle_type_id');
      if (!mform || !select) return;
      mform.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = mform.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var nameEl = mform.querySelector('input[name="name"]');
        var name = nameEl ? (nameEl.value || '').trim() : '';
        if (!name) { showNotification('أدخل اسم النوع', 'warning'); if (btn) btn.disabled = false; return; }
        var url = mform.getAttribute('data-url') || mform.action || window.location.href;
        postForm(url, mform)
          .then(function (data) {
            if (!data || !data.id) throw new Error(data && data.error ? data.error : 'استجابة غير متوقعة');
            appendAndSelectOption(select, data.id, data.name || name);
            showNotification('تمت إضافة النوع.', 'success');
            if (window.jQuery) jQuery(mform).closest('.modal').modal('hide');
            mform.reset();
          })
          .catch(function (err) {
            showNotification('تعذر إضافة النوع: ' + (err && err.message ? err.message : 'خطأ غير معروف'), 'danger');
          })
          .finally(function () { if (btn) btn.disabled = false; });
      });
    })();
    (function initSupplierModal() {
      var mform = document.getElementById('create-supplier-form');
      if (!mform) return;
      mform.addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = mform.querySelector('button[type="submit"]');
        if (btn) btn.disabled = true;
        var payload = {
          name: ((mform.querySelector('input[name="name"]') || {}).value || '').trim(),
          phone: ((mform.querySelector('input[name="phone"]') || {}).value || '').trim(),
          identity_number: ((mform.querySelector('input[name="identity_number"]') || {}).value || '').trim(),
          address: ((mform.querySelector('input[name="address"]') || {}).value || '').trim(),
          notes: ((mform.querySelector('textarea[name="notes"]') || {}).value || '').trim()
        };
        if (!payload.name) { showNotification('الاسم مطلوب', 'warning'); if (btn) btn.disabled = false; return; }
        var url = mform.getAttribute('data-url') || mform.action || window.location.href;
        postJSON(url, payload)
          .then(function (data) {
            if (!data || !data.id) throw new Error(data && data.error ? data.error : 'استجابة غير متوقعة');
            var fallback = document.querySelector('#vendors-container select[name="supplier_id"]');
            var select = window.lastSupplierSelect || fallback;
            if (select) appendAndSelectOption(select, data.id, data.name || payload.name);
            showNotification('تمت إضافة المورّد.', 'success');
            if (window.jQuery) jQuery(mform).closest('.modal').modal('hide');
            mform.reset();
          })
          .catch(function (err) {
            showNotification('تعذر إضافة المورّد: ' + (err && err.message ? err.message : 'خطأ غير معروف'), 'danger');
          })
          .finally(function () { if (btn) btn.disabled = false; });
      });
    })();
    if (form) {
      form.addEventListener('submit', function (e) {
        if (window.jQuery) {
          var vCat = window.jQuery('#category_id').val();
          if (vCat != null) {
            var catEl = document.querySelector('select#category_id');
            if (catEl) catEl.value = Array.isArray(vCat) ? vCat[0] : vCat;
          }
          var vType = window.jQuery('#vehicle_type_id').val();
          if (vType != null) {
            var typeEl = document.querySelector('select#vehicle_type_id');
            if (typeEl) typeEl.value = Array.isArray(vType) ? vType[0] : vType;
          }
        }
        if (wtype === 'PARTNER') {
          if (!validatePartnerSection()) {
            e.preventDefault();
            e.stopPropagation();
            return false;
          }
        }
        if (wtype === 'EXCHANGE') {
          if (!validateExchangeSection()) {
            e.preventDefault();
            e.stopPropagation();
            return false;
          }
        }
        return true;
      });
    }
    (function initBarcode() {
      var input = document.getElementById('barcode');
      var help  = document.getElementById('barcodeHelp');
      if (!input) return;
      var validateURL = input.getAttribute('data-barcode-url') || '';
      input.addEventListener('input', function () {
        var v = input.value.replace(/\D+/g, '');
        if (v.length > 13) v = v.slice(0, 13);
        input.value = v;
        input.classList.remove('is-invalid', 'is-valid');
        if (v.length >= 12 && validateURL) check(v);
      });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          var ff = input.closest('form');
          if (!ff) return;
          var focusables = ff.querySelectorAll('input,select,textarea,button');
          for (var i = 0; i < focusables.length; i++) {
            if (focusables[i] === input && focusables[i + 1]) { focusables[i + 1].focus(); break; }
          }
        }
      });
      function check(code) {
        if (!validateURL) return;
        fetch(validateURL + (validateURL.indexOf('?') >= 0 ? '&' : '?') + 'code=' + encodeURIComponent(code), {
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin'
        })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          if (!res.valid) {
            input.classList.add('is-invalid');
            if (help) help.textContent = 'باركود غير صالح';
            return;
          }
          if (res.normalized && res.normalized !== input.value) {
            input.value = res.normalized;
          }
          if (res.exists) {
            input.classList.add('is-invalid');
            if (help) help.textContent = 'الباركود مستخدم بالفعل';
          } else {
            input.classList.add('is-valid');
            if (help) help.textContent = 'الباركود صالح';
          }
        })
        .catch(function () {
          if (help) help.textContent = 'تعذر التحقق الآن، سيتم الفحص عند الحفظ';
        });
      }
    })();
    bindTransferForm('#transfer-form');
    bindTransferForm('#transferForm');
    bindExchangeForm('#exchange-form');
    bindStockForms();
    wireQuickPicker();
    wireBarcodePick();
    initShipmentsTable();
    setDefaultSourceIfPossible();
    initInventoryDataTable();
    initExpandedToggle();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPage);
  } else {
    initPage();
  }
})();

(function bindTransferInline() {
  var form1 = document.getElementById('transferForm');
  var form2 = document.getElementById('transfer-form');
  function bind(form) {
    if (!form || form.__boundLegacyTransfer) return;
    form.__boundLegacyTransfer = true;
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      postForm(form.action || window.location.href, form)
        .then(function (res) {
          if (res && (res.ok === true || res.success === true)) {
            showNotification(res.message || 'تم تحويل الكمية بنجاح.', 'success');
            if (res.redirect) { window.location = res.redirect; return; }
          } else {
            var msg = (res && (res.message || res.error)) || 'تعذر تنفيذ التحويل';
            showNotification(msg, 'danger');
          }
        })
        .catch(function (err) {
          showNotification((err && err.message) || 'خطأ غير متوقع', 'danger');
        });
    });
  }
  bind(form1);
  bind(form2);
})();
