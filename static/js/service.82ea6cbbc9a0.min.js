/**
 * وحدة الصيانة المحسّنة - JavaScript
 * Enhanced Service Module - JavaScript
 */
(function () {
  'use strict';

  // ========== دوال مساعدة محسّنة ==========
  function toNum(v) {
    var n = parseFloat(v);
    return isNaN(n) ? 0 : n;
  }

  function round2(v) {
    return (Math.round((toNum(v) + Number.EPSILON) * 100) / 100).toFixed(2);
  }

  // Loading State محسّن
  function showLoading($el) {
    $el.addClass('loading').prop('disabled', true);
  }

  function hideLoading($el) {
    $el.removeClass('loading').prop('disabled', false);
  }

  // ========== إعداد الجدول بدون DataTable ==========
  function dtSafeInit() {
    // DataTable معطّل تماماً - نستخدم Pagination server-side
    // هذا أسرع وأكثر كفاءة مع البيانات الكبيرة
    
    // Select All محسّن
    $('#selectAll').on('change', function () {
      $('.row-select').prop('checked', this.checked);
      updateBulkActionsState();
    });

    $('.row-select').on('change', updateBulkActionsState);

    // Bulk Actions
    $('#bulkDelete').on('click', handleBulkDelete);
    $('#exportCsv').on('click', function () {
      var $btn = $(this);
      showLoading($btn);
      setTimeout(function () {
        window.location.assign('/service/export/csv');
        hideLoading($btn);
      }, 500);
    });
    
    // إضافة Hover effects للصفوف
    $('#servicesTable tbody tr').hover(
      function() {
        $(this).addClass('table-active');
      },
      function() {
        $(this).removeClass('table-active');
      }
    );
  }

  function updateBulkActionsState() {
    var count = $('.row-select:checked').length;
    $('#bulkDelete, #bulkArchive').prop('disabled', count === 0);
    if (count > 0) {
      $('#bulkDelete').html('<i class="fas fa-trash"></i> حذف (' + count + ')');
    } else {
      $('#bulkDelete').html('<i class="fas fa-trash"></i> حذف جماعي');
    }
  }

  function handleBulkDelete() {
    var ids = $('.row-select:checked').map(function () {
      return this.value;
    }).get();

    if (!ids.length) {
      return Swal.fire({
        icon: 'warning',
        title: 'تنبيه',
        text: 'لم يتم تحديد أي طلب',
        confirmButtonText: 'حسناً'
      });
    }

    Swal.fire({
      icon: 'warning',
      title: 'تأكيد الحذف الجماعي',
      text: 'سيتم حذف ' + ids.length + ' طلب (غير قابل للتراجع)',
      showCancelButton: true,
      confirmButtonText: 'نعم، احذف',
      cancelButtonText: 'إلغاء',
      confirmButtonColor: '#dc3545'
    }).then(function (res) {
      if (!res.isConfirmed) return;
      // TODO: إضافة route الحذف الجماعي
      Swal.fire({
        icon: 'info',
        title: 'قيد التطوير',
        text: 'هذه الميزة قيد التطوير',
        confirmButtonText: 'حسناً'
      });
    });
  }

  function smartPost(url) {
    if (!url) return;
    var token = $('input[name="csrf_token"]').first().val() || $('meta[name="csrf-token"]').attr('content') || '';
    var $f = $('<form>', { method: 'POST', action: url, style: 'display:none' });
    if (token) $f.append($('<input>', { type: 'hidden', name: 'csrf_token', value: token }));
    $(document.body).append($f); $f.trigger('submit');
  }

  function bindCommonActions() {
    $(document).on('click', '.btn-delete', function (e) {
      e.preventDefault();
      var $form = $(this).closest('form'); if (!$form.length) return;
      Swal.fire({ icon: 'warning', title: 'تأكيد الحذف', text: 'سيتم حذف السجل نهائيًا', showCancelButton: true, confirmButtonText: 'احذف' })
      .then(function (r) { if (r.isConfirmed) $form.trigger('submit'); });
    });
    $('#printReceiptBtn, #previewReceiptBtn').on('click', function () { var url = $(this).data('url'); if (url) window.open(url, '_blank'); });
    $(document).on('click', '.btn-service-start', function (e) {
      e.preventDefault(); var url = $(this).data('url') || $(this).attr('href');
      Swal.fire({ icon: 'question', title: 'بدء الصيانة؟', showCancelButton: true, confirmButtonText: 'ابدأ' })
      .then(function (r) { if (r.isConfirmed) smartPost(url); });
    });
    $(document).on('click', '.btn-service-complete', function (e) {
      e.preventDefault(); var url = $(this).data('url') || $(this).attr('href');
      Swal.fire({ icon: 'question', title: 'إكمال الصيانة؟', text: 'سيتم احتساب المدة الفعلية وإقفال الاستهلاك.', showCancelButton: true, confirmButtonText: 'أكمل' })
      .then(function (r) { if (r.isConfirmed) smartPost(url); });
    });
  }

  function initSelect2Ajax($el, url) {
    $el.select2({
      theme: 'bootstrap4', width: '100%',
      ajax: {
        url: url, dataType: 'json', delay: 250,
        data: function (p) { return { q: p.term || '', limit: 20 }; },
        processResults: function (data) {
          var arr = Array.isArray(data) ? data : (data.results || data.data || []);
          return { results: arr.map(function (x) { if (typeof x === 'object') { var txt = x.text || x.name || String(x.id); return Object.assign({}, x, { id: x.id, text: txt }); } return { id: x, text: String(x) }; }) };
        }
      },
      minimumInputLength: 0, allowClear: true,
      placeholder: $el.attr('data-placeholder') || 'اختر...'
    });
 // اطلب النتائج الفورية بمجرد فتح القائمة حتى لو term فاضي
 $el.on('select2:open', function () {
   var $search = $('.select2-container--open .select2-search__field');
   if ($search.length && !$search.val()) { $search.trigger('input'); }
 });

  }

  function updateAvailHint($scope, available) {
    var $qtyCol = $scope.find('div:has(input[name="quantity"])').first();
    var $hint = $qtyCol.find('.avail-hint');
    if (!$hint.length) $hint = $('<div/>', { class: 'form-text text-muted mt-1 avail-hint' }).appendTo($qtyCol);
    $hint.text('المتاح في المخزن: ' + (available == null ? '-' : available));
  }

  function recalcPriceFromDiscount($scope) {
    var $price = $scope.find('input[name="unit_price"]');
    var $disc  = $scope.find('input[name="discount"]');
    var base   = toNum($price.data('basePrice'));
    var d      = toNum($disc.val());
    if (base > 0) { var p = base * (1 - (d / 100)); $price.val(round2(p)); }
  }

  function recalcDiscountFromPrice($scope) {
    var $price = $scope.find('input[name="unit_price"]');
    var $disc  = $scope.find('input[name="discount"]');
    var base   = toNum($price.data('basePrice'));
    var p      = toNum($price.val());
    if (base > 0) { var d = ((base - p) / base) * 100; $disc.val(round2(d)); }
  }

  function setQueryParam(url, key, val) {
    var u = new URL(url, window.location.origin);
    if (val == null || val === '') u.searchParams.delete(key); else u.searchParams.set(key, val);
    return u.pathname + (u.search ? u.search : '');
  }

  function buildByWarehouseUrl(tpl, wid) {
    if (!tpl) return '';
    if (/[\?&]wid=/.test(tpl)) return tpl.replace(/wid=\d+/i, 'wid=' + String(wid || 0));
    if (/\/(0|\d+)(?=\/products(?:\/)?$)/.test(tpl)) return tpl.replace(/\/(0|\d+)(?=\/products(?:\/)?$)/, '/' + String(wid || 0));
    return setQueryParam(tpl, 'wid', String(wid || 0));
  }

  function buildProductInfoUrl(tpl, pid, wid) {
    if (!tpl) return '';
    var url = tpl;
    if (/[\?&]pid=/.test(url)) url = url.replace(/pid=\d+/i, 'pid=' + String(pid));
    else if (/\/(0|\d+)(?=\/info(?:\/)?$)/.test(url)) url = url.replace(/\/(0|\d+)(?=\/info(?:\/)?$)/, '/' + String(pid));
    else url = setQueryParam(url, 'pid', String(pid));
    if (wid) url = /[\?&]warehouse_id=/.test(url) ? url.replace(/warehouse_id=\d+/i, 'warehouse_id=' + String(wid)) : setQueryParam(url, 'warehouse_id', String(wid));
    return url;
  }

  function fetchAndFillUnitPrice($scope) {
    var $part  = $scope.find('select[name="part_id"]');
    var $price = $scope.find('input[name="unit_price"]');
    var infoTpl = $part.attr('data-product-info');
    var pid = $part.val(); if (!infoTpl || !pid || !$price.length) return;
    var $wh = $scope.find('select[name="warehouse_id"]'); var wid = $wh.val();
    var url = buildProductInfoUrl(infoTpl, pid, wid);

    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (js) {
        if (!js) return;
        if (js.available != null) updateAvailHint($scope, js.available);
        if (js.price != null && !isNaN(parseFloat(js.price))) {
          var base = toNum(js.price);
          $price.data('basePrice', base);
          $price.val(round2(base));
          var $disc = $scope.find('input[name="discount"]');
          if ($disc.length) $disc.val('0.00');
        }
      })
      .catch(function () {});
  }

  function bindWarehouseProductCascade($scope) {
    if ($scope.data('cascade-bound')) return;
    var $wh = $scope.find('select[name="warehouse_id"]');
    var $pr = $scope.find('select[name="part_id"]');
    var whEndpoint = $wh.attr('data-endpoint');
    var prEndpointTemplate = $pr.attr('data-endpoint-by-warehouse');

    if (whEndpoint && $wh.hasClass('select2')) initSelect2Ajax($wh, whEndpoint);

    function initProductsForWarehouse(wid) {
      if (!prEndpointTemplate) return;
      var url = buildByWarehouseUrl(prEndpointTemplate, wid);
      if ($pr.data('select2')) $pr.select2('destroy');
      $pr.val(null).trigger('change');
      initSelect2Ajax($pr, url);
    }

    if ($pr.hasClass('select2') && $wh.val()) initProductsForWarehouse($wh.val());

    $wh.on('change', function () {
      var wid = $(this).val();
      initProductsForWarehouse(wid);
      if ($pr.val()) fetchAndFillUnitPrice($scope);
    });

    $pr.on('select2:select change', function () { fetchAndFillUnitPrice($scope); });

    $scope.data('cascade-bound', true);
  }

  function bootSelect2Auto() {
    $('.select2').each(function () {
      var $el = $(this);
      if ($el.data('bound')) return;
      var ep = $el.attr('data-endpoint');
      if (ep) initSelect2Ajax($el, ep);
      $el.data('bound', true);
    });
  }

  function bindServicePartForm() {
    var $formPart = $('#form-add-part'); if (!$formPart.length) return;
    var $disc = $formPart.find('input[name="discount"]');
    if ($disc.length) { $disc.attr('min', '-100'); $disc.attr('max', '100'); }
    bindWarehouseProductCascade($formPart);
    fetchAndFillUnitPrice($formPart);
    $formPart.on('input change', 'input[name="discount"]', function () { recalcPriceFromDiscount($formPart); });
    $formPart.on('input change', 'input[name="unit_price"]', function () { recalcDiscountFromPrice($formPart); });
  }

  function bindDynamicRows() {
    $('#addPartBtn, #add-part').on('click', function () {
      var tpl =
        '<div class="row g-2 align-items-end mb-2 part-line">' +
          '<div class="col-md-3">' +
            '<label class="form-label d-block">المستودع</label>' +
            '<select class="form-select select2" name="warehouse_id" data-endpoint="/api/search_warehouses"></select>' +
          '</div>' +
          '<div class="col-md-3">' +
            '<label class="form-label d-block">القطعة</label>' +
            '<select class="form-select select2" name="part_id" data-endpoint-by-warehouse="/api/warehouses/0/products" data-product-info="/api/products/0/info"></select>' +
          '</div>' +
          '<div class="col-md-2"><label class="form-label">الكمية</label><input type="number" min="1" class="form-control" name="quantity" value="1"></div>' +
          '<div class="col-md-2"><label class="form-label">سعر الوحدة</label><input type="number" step="0.01" min="0" class="form-control" name="unit_price"></div>' +
          '<div class="col-auto"><label class="form-label d-block">&nbsp;</label><button type="button" class="btn btn-outline-danger remove-part">&times;</button></div>' +
        '</div>';
      $('#parts-list').append(tpl);
      var $row = $('#parts-list .part-line').last();
      $row.find('.select2').each(function () { var $el = $(this); if ($el.data('bound')) return; var ep = $el.attr('data-endpoint'); if (ep) initSelect2Ajax($el, ep); $el.data('bound', true); });
      var $d = $row.find('input[name="discount"]'); if ($d.length) { $d.attr('min','-100').attr('max','100'); }
      bindWarehouseProductCascade($row);
      $row.on('input change', 'input[name="discount"]', function () { recalcPriceFromDiscount($row); });
      $row.on('input change', 'input[name="unit_price"]', function () { recalcDiscountFromPrice($row); });
    });

    $(document).on('click', '.remove-part', function () { $(this).closest('.part-line').remove(); });

    $('#addTaskBtn, #add-task').on('click', function () {
      var tpl =
        '<div class="row g-2 align-items-end mb-2 task-line">' +
          '<div class="col-md-6"><input type="text" class="form-control" name="description" placeholder="الوصف"></div>' +
          '<div class="col-md-2"><input type="number" min="1" class="form-control" name="quantity" value="1"></div>' +
          '<div class="col-md-2"><input type="number" step="0.01" class="form-control" name="unit_price"></div>' +
          '<div class="col-auto"><button type="button" class="btn btn-outline-danger remove-task">&times;</button></div>' +
        '</div>';
      $('#tasks-list').append(tpl);
    });

    $(document).on('click', '.remove-task', function () { $(this).closest('.task-line').remove(); });
  }

  // ========== تحسينات UX إضافية ==========
  
  // Smooth Scroll للعناصر
  function initSmoothScroll() {
    $('a[href^="#"]').on('click', function(e) {
      var target = $(this.getAttribute('href'));
      if (target.length) {
        e.preventDefault();
        $('html, body').stop().animate({
          scrollTop: target.offset().top - 100
        }, 600, 'swing');
      }
    });
  }

  // Tooltips محسّن
  function initTooltips() {
    if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
      var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"], [title]'));
      tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
      });
    }
  }

  // Auto-save form drafts (localStorage)
  function initFormAutoSave() {
    var $forms = $('form[data-autosave]');
    $forms.each(function() {
      var $form = $(this);
      var formId = $form.data('autosave') || 'service_form';
      
      // استعادة من localStorage
      var saved = localStorage.getItem(formId);
      if (saved) {
        try {
          var data = JSON.parse(saved);
          Object.keys(data).forEach(function(key) {
            var $field = $form.find('[name="' + key + '"]');
            if ($field.length) {
              $field.val(data[key]);
            }
          });
        } catch (e) {        }
      }
      
      // حفظ تلقائي
      $form.on('input change', 'input, textarea, select', debounce(function() {
        var data = {};
        $form.find('input, textarea, select').each(function() {
          var $field = $(this);
          var name = $field.attr('name');
          if (name) {
            data[name] = $field.val();
          }
        });
        localStorage.setItem(formId, JSON.stringify(data));
      }, 1000));
      
      // حذف عند Submit
      $form.on('submit', function() {
        localStorage.removeItem(formId);
      });
    });
  }

  // Debounce helper
  function debounce(func, wait) {
    var timeout;
    return function() {
      var context = this, args = arguments;
      clearTimeout(timeout);
      timeout = setTimeout(function() {
        func.apply(context, args);
      }, wait);
    };
  }

  // ========== التهيئة الرئيسية ==========
  $(document).ready(function () {
    dtSafeInit();
    bindCommonActions();
    bootSelect2Auto();
    bindServicePartForm();
    bindDynamicRows();
    initSmoothScroll();
    initTooltips();
    initFormAutoSave();
    
    // Fade in animation
    $('.card, .small-box').css('opacity', 0).animate({ opacity: 1 }, 600);
  });

  // Performance: تنظيف الموارد عند الخروج
  $(window).on('beforeunload', function() {
    // تنظيف localStorage القديمة
    try {
      var keys = Object.keys(localStorage);
      var oneWeekAgo = Date.now() - (7 * 24 * 60 * 60 * 1000);
      keys.forEach(function(key) {
        if (key.startsWith('service_form_')) {
          try {
            var data = JSON.parse(localStorage.getItem(key));
            if (data.timestamp && data.timestamp < oneWeekAgo) {
              localStorage.removeItem(key);
            }
          } catch (e) {
            // Ignore
          }
        }
      });
    } catch (e) {
      // Ignore
    }
  });
  
})();
