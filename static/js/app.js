(function ($) {
  "use strict";
  if (!$) return;

  $(function () {
    const observer = new MutationObserver(() => {
      if (window._mutationPending) return;
      window._mutationPending = true;
      setTimeout(() => {
        window._mutationPending = false;
        initAll(document);
      }, 60);
    });
    observer.observe(document.body, { childList: true, subtree: true });

    $(document).on("shown.bs.modal", e => initAll(e.target || document));

    initAll(document);
    
    // Enhanced performance optimizations
    initPerformanceOptimizations();
    
    // Initialize real-time notifications
    initNotifications();
  });

  function initAll(root) {
    initModalStacking(root);
    installBootstrapCompat(root);
    initDataTables(root);
    initDatepickers(root);
    initSelect2Basic(root);
    initTooltips(root);
    initPerformanceOptimizations(root);
    initAjaxSelects(root);
    initConfirmForms(root);
    initBtnLoading(root);
  }

  function initModalStacking(root) {
    if (!$ || !$.fn || !$.fn.modal) return;

    ensureModalCompatStyles();

    var $root = root && root.nodeType ? $(root) : $(document);
    $root.find(".modal").each(function () {
      normalizeModalParent($(this));
    });

    if (window.__azadModalStackingBound) return;
    window.__azadModalStackingBound = true;

    $(document)
      .on("show.bs.modal", ".modal", function () {
        var $modal = $(this);
        normalizeModalParent($modal);
        $("body").addClass("azad-modal-open");
      })
      .on("shown.bs.modal", ".modal", function () {
        fixModalLayering();
      })
      .on("hidden.bs.modal", ".modal", function () {
        window.setTimeout(cleanupModalArtifacts, 0);
      });
  }

  function ensureModalCompatStyles() {
    if (document.getElementById("azad-modal-compat-style")) return;

    var style = document.createElement("style");
    style.id = "azad-modal-compat-style";
    style.textContent = [
      ".modal-backdrop { z-index: 2040 !important; }",
      ".modal { z-index: 2050 !important; }",
      ".modal-dialog, .modal-content { pointer-events: auto; }"
    ].join("\n");
    document.head.appendChild(style);
  }

  function normalizeModalParent($modal) {
    if (!$modal || !$modal.length) return;
    if ($modal.parent()[0] !== document.body) {
      $modal.appendTo(document.body);
    }
  }

  function fixModalLayering() {
    var modalBase = 2050;
    $(".modal.show").each(function (index) {
      $(this).css("z-index", modalBase + (index * 20));
    });
    $(".modal-backdrop").each(function (index) {
      $(this).css("z-index", (modalBase - 10) + (index * 20));
    });
  }

  function cleanupModalArtifacts() {
    if ($(".modal.show").length === 0) {
      $(".modal-backdrop").remove();
      $("body").removeClass("modal-open azad-modal-open").css("padding-right", "");
      return;
    }
    fixModalLayering();
  }

  function installBootstrapCompat(root) {
    if (!$ || !$.fn) return;

    var $root = root && root.nodeType ? $(root) : $(document);

    $root.find("[data-bs-toggle]").each(function () {
      var $el = $(this);
      if (!$el.attr("data-toggle")) {
        $el.attr("data-toggle", $el.attr("data-bs-toggle"));
      }
    });

    $root.find("[data-bs-target]").each(function () {
      var $el = $(this);
      if (!$el.attr("data-target")) {
        $el.attr("data-target", $el.attr("data-bs-target"));
      }
    });

    $root.find("[data-bs-dismiss]").each(function () {
      var $el = $(this);
      if (!$el.attr("data-dismiss")) {
        $el.attr("data-dismiss", $el.attr("data-bs-dismiss"));
      }
    });

    $root.find(".btn-close").each(function () {
      var $btn = $(this);
      if (!$btn.hasClass("close")) {
        $btn.addClass("close");
      }
      if (!$btn.attr("type")) {
        $btn.attr("type", "button");
      }
      if (!$btn.attr("aria-label")) {
        $btn.attr("aria-label", "Close");
      }
      if (!$btn.attr("data-dismiss") && $btn.attr("data-bs-dismiss")) {
        $btn.attr("data-dismiss", $btn.attr("data-bs-dismiss"));
      }
      if (!$btn.children().length && !$btn.text().trim()) {
        $btn.html('<span aria-hidden="true">&times;</span>');
      }
    });

    installBootstrapFacade();
  }

  function installBootstrapFacade() {
    if (!$ || !$.fn) return;

    if (!window.__bootstrapCompatDelegatesBound) {
      window.__bootstrapCompatDelegatesBound = true;

      $(document)
        .on("click", "[data-bs-toggle=\"modal\"]", function (e) {
          var target = $(this).attr("data-bs-target") || $(this).attr("href");
          if (!target || target === "#") return;
          e.preventDefault();
          $(target).modal("show");
        })
        .on("click", "[data-bs-dismiss=\"modal\"]", function (e) {
          e.preventDefault();
          $(this).closest(".modal").modal("hide");
        })
        .on("click", "[data-bs-dismiss=\"alert\"]", function (e) {
          e.preventDefault();
          $(this).closest(".alert").alert("close");
        })
        .on("click", "[data-bs-toggle=\"tab\"], [data-bs-toggle=\"pill\"]", function (e) {
          e.preventDefault();
          $(this).tab("show");
        });
    }

    window.bootstrap = window.bootstrap || {};

    if (!window.bootstrap.Modal && $.fn.modal) {
      function Modal(element) {
        this._element = element;
      }
      Modal.prototype.show = function () { $(this._element).modal("show"); };
      Modal.prototype.hide = function () { $(this._element).modal("hide"); };
      Modal.prototype.toggle = function () { $(this._element).modal("toggle"); };
      Modal.prototype.dispose = function () { $(this._element).modal("hide"); };
      Modal.getInstance = function (element) {
        return $(element).data("bs.modal") ? new Modal(element) : null;
      };
      Modal.getOrCreateInstance = function (element) {
        return new Modal(element);
      };
      window.bootstrap.Modal = Modal;
    }

    if (!window.bootstrap.Tooltip && $.fn.tooltip) {
      function Tooltip(element, options) {
        this._element = element;
        $(element).tooltip(options || {});
      }
      Tooltip.prototype.show = function () { $(this._element).tooltip("show"); };
      Tooltip.prototype.hide = function () { $(this._element).tooltip("hide"); };
      Tooltip.prototype.toggle = function () { $(this._element).tooltip("toggle"); };
      Tooltip.prototype.dispose = function () { $(this._element).tooltip("dispose"); };
      Tooltip.getInstance = function (element) {
        return $(element).data("bs.tooltip") ? new Tooltip(element) : null;
      };
      Tooltip.getOrCreateInstance = function (element, options) {
        return new Tooltip(element, options);
      };
      window.bootstrap.Tooltip = Tooltip;
    }

    if (!window.bootstrap.Tab && $.fn.tab) {
      function Tab(element) {
        this._element = element;
      }
      Tab.prototype.show = function () { $(this._element).tab("show"); };
      Tab.getInstance = function (element) {
        return $(element).data("bs.tab") ? new Tab(element) : null;
      };
      Tab.getOrCreateInstance = function (element) {
        return new Tab(element);
      };
      window.bootstrap.Tab = Tab;
    }

    if (!window.bootstrap.Alert && $.fn.alert) {
      function Alert(element) {
        this._element = element;
      }
      Alert.prototype.close = function () { $(this._element).alert("close"); };
      Alert.getInstance = function (element) {
        return $(element).data("bs.alert") ? new Alert(element) : null;
      };
      Alert.getOrCreateInstance = function (element) {
        return new Alert(element);
      };
      window.bootstrap.Alert = Alert;
    }
  }

  function initTooltips(root) {
    if (!$.fn.tooltip) return;
    var $root = root && root.nodeType ? $(root) : $(document);
    $root.find("[data-toggle=\"tooltip\"]").each(function () {
      var $el = $(this);
      if ($el.data("bs.tooltip")) return;
      $el.tooltip({ trigger: "hover", html: true });
    });
  }

  function initDataTables(root) {
    if (!$.fn.DataTable) return;
    $(root).find(".datatable").each(function () {
      const $tbl = $(this);
      if ($.fn.DataTable.isDataTable(this)) return;
      if ($tbl.data("dt-initialized")) return;
      $tbl.data("dt-initialized", 1);

      const hasButtons = $.fn.dataTable?.Buttons;
      const pageLen = +$tbl.data("page-length") || 10;
      const orderAttr = String($tbl.data("order") || "").trim();
      const order = orderAttr.match(/^(\d+)\s*,\s*(asc|desc)$/i)
        ? [[+RegExp.$1, RegExp.$2.toLowerCase()]]
        : [];

      const noSortIdx = $tbl.find("thead th.dt-nosort").map((i, el) => i).get();

      $tbl.DataTable({
        dom: hasButtons ? "Bfrtip" : "frtip",
        buttons: hasButtons ? [
          { extend: "excelHtml5", text: '<i class="fas fa-file-excel"></i> Excel' },
          { extend: "print", text: '<i class="fas fa-print"></i> طباعة', customize: function(win) { applyDataTablePrintStyles(win); } }
        ] : [],
        pageLength: pageLen,
        responsive: true,
        autoWidth: false,
        language: { url: "/static/datatables/Arabic.json" },
        order,
        columnDefs: noSortIdx.length ? [{ orderable: false, targets: noSortIdx }] : []
      });
    });
  }

  function initDatepickers(root) {
    if (!$.fn.datepicker) return;
    $(root).find(".datepicker").each(function () {
      const $el = $(this);
      if ($el.data("dp-initialized")) return;
      $el.data("dp-initialized", 1).datepicker({
        format: "yyyy-mm-dd",
        autoclose: true,
        language: "ar",
        orientation: "auto right",
        todayHighlight: true
      });
    });
  }

  function initSelect2Basic(root) {
    if (!$.fn.select2) return;
    // تجنب التداخل مع customer-select.js و supplier-select
    $(root).find("select.select2:not(.ajax-select):not(.customer-select):not(.supplier-select)").not('.select2-hidden-accessible').each(function () {
      const $el = $(this);
      if ($el.data("s2-initialized")) return;
      $el.data("s2-initialized", 1);
      const parent = $el.closest(".modal");
      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        allowClear: String($el.data("allow-clear") || "").toLowerCase() === "true" || $el.data("allowClear") == 1,
        dropdownParent: parent.length ? parent : $(document.body)
      });
    });
  }

  function initAjaxSelects(root) {
    if (!$.fn.select2) return;
    // تجنب التداخل مع customer-select.js و supplier-select
    $(root).find("select.ajax-select:not(.customer-select):not(.supplier-select)").each(function () {
      const $el = $(this);
      if ($el.data("s2-initialized")) return;
      $el.data("s2-initialized", 1);

      const url = $el.data("url") || $el.data("endpoint");
      if (!url) return;

      const parent = $el.closest(".modal");
      const delay = +$el.data("delay") || 250;
      const limit = +$el.data("limit") || 20;
      const minLen = +$el.data("min-length") || 0;

      $el.select2({
        dir: "rtl",
        width: "100%",
        language: "ar",
        placeholder: $el.attr("placeholder") || "اختر...",
        allowClear: String($el.data("allow-clear") || "").toLowerCase() === "true" || $el.data("allowClear") == 1,
        minimumInputLength: minLen,
        dropdownParent: parent.length ? parent : $(document.body),
        ajax: {
          url,
          dataType: "json",
          delay,
          cache: true,
          data: params => ({ q: params.term || "", limit }),
          processResults: data => ({
            results: (Array.isArray(data) ? data : (data.results || data.data || [])).map(x => ({
              id: x.id,
              text: x.text || x.name || String(x.id)
            }))
          })
        }
      });

      const val = $el.val();
      const txt = $el.data("initial-text");
      if (val && txt && !$el.find('option[value="' + val + '"]').length) {
        $el.append(new Option(txt, val, true, true)).trigger("change");
      }
    });
  }

  function initConfirmForms(root) {
    $(root).find("form[data-confirm]").each(function () {
      const $form = $(this);
      if ($form.data("confirm-bound")) return;
      $form.data("confirm-bound", 1).on("submit", function (e) {
        const msg = $form.data("confirm");
        if (msg && !confirm(msg)) {
          e.preventDefault();
          e.stopImmediatePropagation();
        }
      });
    });
  }

  function initBtnLoading(root) {
    $(root).find(".btn-loading").each(function () {
      const $btn = $(this);
      if ($btn.data("loading-bound")) return;
      $btn.data("loading-bound", 1).on("click", function () {
        if ($btn.prop("disabled")) return;
        const original = $btn.html();
        $btn.data("original-html", original).prop("disabled", true).attr("aria-busy", "true")
          .html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> جاري المعالجة...');
        setTimeout(() => {
          if (!$btn.closest("form").length) {
            $btn.prop("disabled", false).attr("aria-busy", "false").html(original);
          }
        }, 10000);
      });
    });
  }

  // Enhanced performance optimizations
  function initPerformanceOptimizations(root) {
    // Lazy loading for images
    if ('IntersectionObserver' in window) {
      const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            const img = entry.target;
            img.src = img.dataset.src;
            img.classList.remove('lazy');
            imageObserver.unobserve(img);
          }
        });
      });

      $(root).find('img[data-src]').each(function() {
        imageObserver.observe(this);
      });
    }

    // Debounced search
    let searchTimeout;
    $(root).find('[data-search]').off('.erpSearch').on('input.erpSearch', function() {
      clearTimeout(searchTimeout);
      const $this = $(this);
      searchTimeout = setTimeout(() => {
        performSearch($this.val(), $this.data('search'));
      }, 300);
    });

    // Auto-save forms
    $(root).find('[data-autosave]').off('.erpAutoSave').on('input change.erpAutoSave', debounce(function() {
      saveFormData($(this).closest('form'));
    }, 1000));

  }

  function performSearch(query, target) {
    if (query.length < 2) return;
    
    const $container = $(`[data-search-target="${target}"]`);
    $container.html('<div class="text-center"><div class="spinner-border"></div></div>');
    
    $.get('/api/search', { type: target, q: query })
      .done(data => {
        if (data.html) {
          $container.html(data.html);
        } else if (data.results && data.results.length) {
          $container.html('<ul class="list-group">' + data.results.map(r =>
            '<li class="list-group-item d-flex justify-content-between align-items-center">' +
            (r.text || r.name || '') +
            (r.phone ? '<span class="badge badge-secondary">' + r.phone + '</span>' : '') +
            '</li>'
          ).join('') + '</ul>');
        } else {
          $container.html('لا توجد نتائج');
        }
      })
      .fail(() => {
        $container.html('<div class="alert alert-danger">خطأ في البحث</div>');
      });
  }

  function saveFormData($form) {
    const formData = $form.find('input, select, textarea').not('[type="password"], [type="hidden"], [name*="csrf"], [name*="token"], [name*="secret"], [name*="api_key"], [name*="password"]').serialize();
    localStorage.setItem(`form_${$form.attr('id')}`, formData);
    showNotification('تم الحفظ', 'تم حفظ البيانات تلقائياً', 'success');
  }

  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  function initNotifications() {
    if (typeof io === 'undefined') {
      // Socket.IO غير مطلوب للنظام الأساسي
      return;
    }

    const socket = io();
    
    // إشعارات المستخدم
    socket.on('notification', function(data) {
      showNotification(data.title, data.message, data.type);
    });
    
    // إشعارات عامة
    socket.on('broadcast_notification', function(data) {
      showNotification(data.title, data.message, data.type);
    });
    
    // تنبيهات النظام
    socket.on('system_alert', function(data) {
      showSystemAlert(data.message, data.severity);
    });
    
    // اتصال المستخدم بالغرفة
    socket.emit('join_user_room');
  }

  function showNotification(title, message, type = 'info') {
    const alertClass = {
      'success': 'alert-success',
      'error': 'alert-danger',
      'warning': 'alert-warning',
      'info': 'alert-info'
    }[type] || 'alert-info';
    
    const icon = {
      'success': 'fas fa-check-circle',
      'error': 'fas fa-exclamation-circle',
      'warning': 'fas fa-exclamation-triangle',
      'info': 'fas fa-info-circle'
    }[type] || 'fas fa-info-circle';
    
    const $notification = $(`
      <div class="alert ${alertClass} alert-dismissible fade show notification-toast" role="alert">
        <i class="${icon} me-2"></i>
        <strong>${title}</strong><br>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    `);
    
    // إضافة للصفحة
    let $container = $('#notification-container');
    if ($container.length === 0) {
      $container = $('<div id="notification-container" style="position: fixed; top: 20px; right: 20px; z-index: 9999; max-width: 350px;"></div>');
      $('body').append($container);
    }
    
    $container.append($notification);
    
    // إزالة تلقائية
    setTimeout(() => {
      $notification.alert('close');
    }, 5000);
  }

  function showSystemAlert(message, severity = 'warning') {
    const alertClass = {
      'critical': 'alert-danger',
      'warning': 'alert-warning',
      'info': 'alert-info'
    }[severity] || 'alert-warning';
    
    const icon = {
      'critical': 'fas fa-exclamation-triangle',
      'warning': 'fas fa-exclamation-triangle',
      'info': 'fas fa-info-circle'
    }[severity] || 'fas fa-exclamation-triangle';
    
    const $alert = $(`
      <div class="alert ${alertClass} alert-dismissible fade show system-alert" role="alert">
        <i class="${icon} me-2"></i>
        <strong>تنبيه النظام:</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    `);
    
    // إضافة للصفحة
    let $container = $('#system-alert-container');
    if ($container.length === 0) {
      $container = $('<div id="system-alert-container" style="position: fixed; top: 20px; left: 20px; z-index: 9999; max-width: 400px;"></div>');
      $('body').append($container);
    }
    
    $container.append($alert);
    
    // إزالة تلقائية
    setTimeout(() => {
      $alert.alert('close');
    }, 10000);
  }

  // ── Shared print helpers ──

  /**
   * AzadPrint.printPageReport() - clean window.print() for report/ledger pages.
   * Adds .is-printing class to body before print, removes after.
   * Use with: <button onclick="AzadPrint.printPageReport()">
   */
  window.AzadPrint = {
    printPageReport: function() {
      document.body.classList.add('is-printing-report');
      setTimeout(function() {
        window.print();
        setTimeout(function() {
          document.body.classList.remove('is-printing-report');
        }, 500);
      }, 100);
    },
    printElement: function(selector, options) {
      var $el = $(selector);
      if (!$el.length) return;
      var $clone = $el.clone();
      var $printWin = window.open('', '_blank', 'width=1200,height=800');
      if (!$printWin) return;
      $printWin.document.write('<!DOCTYPE html><html dir="rtl"><head><title>' + (options && options.title || 'طباعة') + '</title>');
      $printWin.document.write('<style>body { font-family: "Cairo", Tahoma, sans-serif; font-size: 10pt; direction: rtl; background: #fff; padding: 10mm; } table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #adb5bd; padding: 2mm 3mm; text-align: center; } thead th { background: ' + (options && options.headerColor || '#0d6efd') + '; color: #fff; } thead { display: table-header-group; } tfoot { display: table-footer-group; } tr { page-break-inside: avoid; } @page { size: A4 landscape; margin: 10mm; }</style></head><body>');
      $printWin.document.write($clone[0].outerHTML);
      $printWin.document.write('</body></html>');
      $printWin.document.close();
      setTimeout(function() { $printWin.print(); $printWin.close(); }, 500);
    }
  };

  // Shared print styles for DataTables print windows
  window.applyDataTablePrintStyles = function(win) {
    if (!win || !win.document) return;
    const css = [
      '@page { size: A4 landscape; margin: 10mm; }',
      'body { font-size: 9pt; direction: rtl; font-family: "Cairo", "Tahoma", sans-serif; -webkit-print-color-adjust: exact; background: #fff; }',
      'h1 { text-align: center; font-size: 12pt; margin-bottom: 3mm; }',
      '.table-responsive { overflow: visible !important; width: 100% !important; }',
      'table { width: 100% !important; max-width: 100% !important; table-layout: auto !important; border-collapse: collapse !important; }',
      'table th, table td { border: 1px solid #adb5bd !important; padding: 2mm 3mm !important; text-align: center !important; vertical-align: middle; white-space: normal !important; word-break: break-word; }',
      'table thead th { background: #0d6efd !important; color: #fff !important; }',
      'thead { display: table-header-group; }',
      'tfoot { display: table-footer-group; }',
      'tr { page-break-inside: avoid; break-inside: avoid; }',
      'th, td { white-space: normal !important; overflow: visible !important; word-break: break-word; overflow-wrap: anywhere; }'
    ].join('\n');
    const style = win.document.createElement('style');
    style.type = 'text/css';
    style.appendChild(win.document.createTextNode(css));
    win.document.head.appendChild(style);
  };
})(jQuery);
