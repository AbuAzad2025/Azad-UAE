(function (window, $) {
  'use strict';

  const hasPrintExtension = $ &&
    $.fn &&
    $.fn.dataTable &&
    $.fn.dataTable.Buttons &&
    $.fn.dataTable.ext &&
    $.fn.dataTable.ext.buttons &&
    $.fn.dataTable.ext.buttons.print &&
    typeof $.fn.dataTable.ext.buttons.print.action === 'function';

  let defaultPrintAction = null;

  if (!hasPrintExtension) {
    console.warn('SmartPrint: DataTables Buttons with print extension is required.');
  } else {
    defaultPrintAction = $.fn.dataTable.ext.buttons.print.action;
  }
  let modalInitialized = false;
  const triggerRegistry = new WeakMap();
  const state = {
    table: null,
    buttonApi: null,
    options: null
  };

  function ensureModal() {
    if (modalInitialized) {
      return;
    }

    const modalHtml = [
      '<div class="modal fade" id="smartPrintModal" tabindex="-1" role="dialog" aria-labelledby="smartPrintModalLabel" aria-hidden="true">',
      '  <div class="modal-dialog modal-dialog-centered" role="document">',
      '    <div class="modal-content">',
      '      <div class="modal-header">',
      '        <h5 class="modal-title" id="smartPrintModalLabel"><i class="fas fa-print mr-2"></i>خيارات الطباعة المتقدمة</h5>',
      '        <button type="button" class="close" data-dismiss="modal" aria-label="Close">',
      '          <span aria-hidden="true">&times;</span>',
      '        </button>',
      '      </div>',
      '      <div class="modal-body">',
      '        <div class="alert alert-danger d-none" id="smartPrintError"></div>',
      '        <div class="custom-control custom-radio mb-2">',
      '          <input type="radio" class="custom-control-input" name="smartPrintRange" id="smartPrintAll" value="all" checked>',
      '          <label class="custom-control-label" for="smartPrintAll">طباعة جميع الصفوف</label>',
      '        </div>',
      '        <div class="custom-control custom-radio mb-2">',
      '          <input type="radio" class="custom-control-input" name="smartPrintRange" id="smartPrintPage" value="page">',
      '          <label class="custom-control-label" for="smartPrintPage">طباعة الصفحة الحالية فقط</label>',
      '        </div>',
      '        <div class="border rounded p-2 mb-3">',
      '          <div class="custom-control custom-radio mb-2">',
      '            <input type="radio" class="custom-control-input" name="smartPrintRange" id="smartPrintRows" value="rows">',
      '            <label class="custom-control-label" for="smartPrintRows">تحديد مدى الأسطر</label>',
      '          </div>',
      '          <div class="form-row">',
      '            <div class="form-group col">',
      '              <label class="small mb-1" for="smartPrintRowStart">من السطر</label>',
      '              <input type="number" min="1" class="form-control form-control-sm" id="smartPrintRowStart" disabled>',
      '            </div>',
      '            <div class="form-group col">',
      '              <label class="small mb-1" for="smartPrintRowEnd">إلى السطر</label>',
      '              <input type="number" min="1" class="form-control form-control-sm" id="smartPrintRowEnd" disabled>',
      '            </div>',
      '          </div>',
      '        </div>',
      '        <div class="border rounded p-2">',
      '          <div class="custom-control custom-radio mb-2">',
      '            <input type="radio" class="custom-control-input" name="smartPrintRange" id="smartPrintPages" value="pages">',
      '            <label class="custom-control-label" for="smartPrintPages">تحديد مدى الصفحات</label>',
      '          </div>',
      '          <div class="form-row">',
      '            <div class="form-group col">',
      '              <label class="small mb-1" for="smartPrintPageStart">من الصفحة</label>',
      '              <input type="number" min="1" class="form-control form-control-sm" id="smartPrintPageStart" disabled>',
      '            </div>',
      '            <div class="form-group col">',
      '              <label class="small mb-1" for="smartPrintPageEnd">إلى الصفحة</label>',
      '              <input type="number" min="1" class="form-control form-control-sm" id="smartPrintPageEnd" disabled>',
      '            </div>',
      '          </div>',
      '        </div>',
      '      </div>',
      '      <div class="modal-footer">',
      '        <button type="button" class="btn btn-secondary" data-dismiss="modal">إلغاء</button>',
      '        <button type="button" class="btn btn-primary" id="smartPrintModalConfirm"><i class="fas fa-print mr-1"></i>طباعة</button>',
      '      </div>',
      '    </div>',
      '  </div>',
      '</div>'
    ].join('');

    $('body').append(modalHtml);

    $('#smartPrintModal').on('hidden.bs.modal', resetModal);
    $('input[name="smartPrintRange"]').on('change', function () {
      updateInputStates(this.value);
    });
    $('#smartPrintModalConfirm').on('click', handleConfirm);

    modalInitialized = true;
  }

  function resetModal() {
    $('#smartPrintError').addClass('d-none').text('');
    $('#smartPrintAll').prop('checked', true);
    $('#smartPrintRowStart, #smartPrintRowEnd, #smartPrintPageStart, #smartPrintPageEnd')
      .prop('disabled', true)
      .val('');
  }

  function updateInputStates(mode) {
    const isRows = mode === 'rows';
    const isPages = mode === 'pages';

    $('#smartPrintRowStart, #smartPrintRowEnd').prop('disabled', !isRows);
    $('#smartPrintPageStart, #smartPrintPageEnd').prop('disabled', !isPages);

    if (!isRows) {
      $('#smartPrintRowStart, #smartPrintRowEnd').val('');
    }
    if (!isPages) {
      $('#smartPrintPageStart, #smartPrintPageEnd').val('');
    }
  }

  function showError(message) {
    $('#smartPrintError').removeClass('d-none').text(message);
  }

  function clearError() {
    $('#smartPrintError').addClass('d-none').text('');
  }

  function openModal(table, buttonApi, options) {
    ensureModal();
    resetModal();
    clearError();

    state.table = table;
    state.buttonApi = buttonApi;
    state.options = options || {};

    $('#smartPrintModal').modal('show');
  }

  function buildRowsSelector(mode, table, values) {
    const appliedIndexes = table.rows({ search: 'applied' }).indexes().toArray();
    if (!appliedIndexes.length) {
      showError('لا توجد صفوف مطابقة للطباعة.');
      return null;
    }

    const includeAll = (idx) => appliedIndexes.indexOf(idx) !== -1;

    if (mode === 'all') {
      return includeAll;
    }

    if (mode === 'page') {
      const currentIndexes = table.rows({ page: 'current' }).indexes().toArray();
      if (!currentIndexes.length) {
        showError('لا توجد صفوف في الصفحة الحالية.');
        return null;
      }
      return (idx) => currentIndexes.indexOf(idx) !== -1;
    }

    const pageInfo = table.page.info();
    const rowsPerPage = pageInfo.length === -1 ? appliedIndexes.length : pageInfo.length;

    if (mode === 'rows') {
      const start = parseInt(values.rowStart, 10);
      const end = values.rowEnd ? parseInt(values.rowEnd, 10) : start;

      if (!start || start < 1 || Number.isNaN(start)) {
        showError('يرجى إدخال رقم سطر بداية صحيح.');
        return null;
      }
      if (!end || end < start || Number.isNaN(end)) {
        showError('يرجى إدخال رقم سطر نهاية صحيح لا يقل عن رقم البداية.');
        return null;
      }
      if (start > appliedIndexes.length) {
        showError('رقم السطر الأول يتجاوز عدد الصفوف المتاحة.');
        return null;
      }
      const cappedEnd = Math.min(end, appliedIndexes.length);
      const startPos = start - 1;
      const endPos = cappedEnd - 1;
      return (idx) => {
        const position = appliedIndexes.indexOf(idx);
        return position !== -1 && position >= startPos && position <= endPos;
      };
    }

    if (mode === 'pages') {
      const pageInfoPages = table.page.info();
      const totalPages = pageInfoPages.pages || 1;
      if (rowsPerPage === -1 || totalPages <= 1) {
        showError('الجدول يعرض كل الصفوف في صفحة واحدة، اختر "جميع الصفوف".');
        return null;
      }

      const startPage = parseInt(values.pageStart, 10);
      const endPage = values.pageEnd ? parseInt(values.pageEnd, 10) : startPage;

      if (!startPage || startPage < 1 || Number.isNaN(startPage)) {
        showError('يرجى إدخال رقم صفحة بداية صحيح.');
        return null;
      }
      if (!endPage || endPage < startPage || Number.isNaN(endPage)) {
        showError('يرجى إدخال رقم صفحة نهاية صحيح لا يقل عن رقم البداية.');
        return null;
      }
      if (startPage > totalPages) {
        showError('رقم الصفحة الأولى يتجاوز عدد الصفحات المتاحة.');
        return null;
      }
      const cappedEndPage = Math.min(endPage, totalPages);
      const startPos = (startPage - 1) * rowsPerPage;
      const endPos = Math.min((cappedEndPage * rowsPerPage) - 1, appliedIndexes.length - 1);
      return (idx) => {
        const position = appliedIndexes.indexOf(idx);
        return position !== -1 && position >= startPos && position <= endPos;
      };
    }

    showError('لم يتم التعرف على خيار الطباعة.');
    return null;
  }

  // Fallback print function when DataTables print extension is missing
  function fallbackPrint(table, config) {
    const dt = table;
    let data = { header: [], body: [], footer: [] };
    let info = { title: '', messageTop: '', messageBottom: '' };

    try {
        if (dt.buttons && typeof dt.buttons.exportData === 'function') {
            data = dt.buttons.exportData(config.exportOptions);
            info = dt.buttons.exportInfo(config);
        } else {
            // Manual extraction from DOM if Buttons extension is missing
            
            // Extract Header
            $(dt.table().header()).find('tr').each(function() {
                let row = [];
                $(this).find('th, td').each(function() {
                    row.push($(this).text().trim());
                });
                // Only take the last header row if multiple exist (common in DT)
                data.header = row; 
            });

            // Extract Body (using current page or all pages based on config?)
            // If we want all data, we might need to use dt.rows().data()
            // config.exportOptions usually specifies modifier: { page: 'all' }
            
            let modifier = (config.exportOptions && config.exportOptions.modifier) || { page: 'all' };
            let rows = dt.rows(modifier).nodes();
            
            if (rows.length === 0) {
                 // Try getting data directly if nodes are not rendered
                 let rawData = dt.rows(modifier).data();
                 for (let i = 0; i < rawData.length; i++) {
                     let rowData = [];
                     // This is tricky because data might be objects or arrays
                     // Simplified assumption: array or object values
                     let item = rawData[i];
                     if (Array.isArray(item)) {
                         rowData = item;
                     } else if (typeof item === 'object') {
                         rowData = Object.values(item);
                     }
                     data.body.push(rowData);
                 }
            } else {
                $(rows).each(function() {
                    let row = [];
                    $(this).find('td').each(function() {
                        row.push($(this).text().trim());
                    });
                    data.body.push(row);
                });
            }

            // Extract Footer
            $(dt.table().footer()).find('tr').each(function() {
                 let row = [];
                $(this).find('th, td').each(function() {
                    row.push($(this).text().trim());
                });
                data.footer = row;
            });
            
            info.title = config.title || document.title;
        }
    } catch (e) {
        console.error('SmartPrint: Data extraction failed', e);
        alert('حدث خطأ أثناء تحضير البيانات للطباعة.');
        return;
    }

    const opts = config.smartPrintOptions || {};

    let html = '<table class="table table-striped table-bordered">';

    // Header
    if (config.header) {
      html += '<thead><tr>';
      for (let i = 0; i < data.header.length; i++) {
        html += '<th>' + data.header[i] + '</th>';
      }
      html += '</tr></thead>';
    }

    // Body
    html += '<tbody>';
    for (let i = 0; i < data.body.length; i++) {
      html += 'tr';
      for (let j = 0; j < data.body[i].length; j++) {
        html += '<td>' + data.body[i][j] + '</td>';
      }
      html += '</tr>';
    }
    html += '</tbody>';

    // Footer
    if (config.footer && data.footer) {
      html += '<tfoot><tr>';
      for (let i = 0; i < data.footer.length; i++) {
        html += '<th>' + data.footer[i] + '</th>';
      }
      html += '</tr></tfoot>';
    }
    html += '</table>';

    // Create a new window for printing
    const win = window.open('', '');
    if (!win) {
      alert('يرجى السماح بالنوافذ المنبثقة لطباعة التقرير.');
      return;
    }

    const title = opts.title || config.title || document.title;
    
    win.document.write('<!DOCTYPE html><html dir="rtl"><head><title>' + title + '</title>');
    win.document.write('<style>');
    win.document.write('body { font-family: "Tajawal", sans-serif; direction: rtl; padding: 20px; }');
    win.document.write('table { width: 100%; border-collapse: collapse; margin-bottom: 1rem; }');
    win.document.write('th, td { border: 1px solid #dee2e6; padding: 0.75rem; text-align: right; }');
    win.document.write('th { background-color: #f8f9fa; font-weight: bold; }');
    win.document.write('.print-header { text-align: center; margin-bottom: 20px; }');
    win.document.write('.print-title { font-size: 24px; font-weight: bold; margin-bottom: 10px; }');
    win.document.write('@media print { body { -webkit-print-color-adjust: exact; } }');
    win.document.write('</style>');
    win.document.write('</head><body>');
    
    win.document.write('<div class="print-header">');
    if (info.title) win.document.write('<h1 class="print-title">' + info.title + '</h1>');
    if (info.messageTop) win.document.write('<div class="message-top">' + info.messageTop + '</div>');
    win.document.write('</div>');
    
    win.document.write(html);
    
    if (info.messageBottom) win.document.write('<div class="message-bottom" style="margin-top: 20px;">' + info.messageBottom + '</div>');
    
    win.document.write('</body></html>');
    
    win.document.close();
    
    // Wait for content to load then print
    setTimeout(function() {
      win.focus();
      win.print();
      win.close();
    }, 500);
  }

  function handleConfirm() {
    if (!state.table || !state.buttonApi) {
      return;
    }

    clearError();
    const mode = $('input[name="smartPrintRange"]:checked').val();
    updateInputStates(mode);

    const rowsSelector = buildRowsSelector(mode, state.table, {
      rowStart: $('#smartPrintRowStart').val(),
      rowEnd: $('#smartPrintRowEnd').val(),
      pageStart: $('#smartPrintPageStart').val(),
      pageEnd: $('#smartPrintPageEnd').val()
    });

    if (typeof rowsSelector !== 'function') {
      return;
    }

    const buttonNode = state.buttonApi.node();
    const originalConfig = $.extend(true, {}, $(buttonNode).data('smartPrintConfig') || {});
    originalConfig.exportOptions = originalConfig.exportOptions || {};
    originalConfig.exportOptions.columns = originalConfig.exportOptions.columns || ':visible';
    originalConfig.exportOptions.rows = rowsSelector;

    $('#smartPrintModal').modal('hide');

    if (defaultPrintAction) {
      try {
        defaultPrintAction.call(state.buttonApi, new $.Event('smart-print'), state.table, buttonNode, originalConfig);
      } catch (e) {
        console.warn('SmartPrint: Standard print failed, trying fallback.', e);
        fallbackPrint(state.table, originalConfig);
      }
    } else {
      fallbackPrint(state.table, originalConfig);
    }
  }

  function applyPrintStyles(win, options) {
    const title = options.title || '';
    const headerColor = options.headerColor || '#0d6efd';

    const css = [
      '@page { size: A4 landscape; margin: 8mm; }',
      'body { font-size: 9pt; direction: rtl; font-family: "Cairo", "Tahoma", sans-serif; -webkit-print-color-adjust: exact; position: relative; }',
      'body::before { content: "تصميم شركة أزاد للأنظمة الذكية"; position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-10deg); font-size: 18pt; color: rgba(108, 117, 125, 0.12); white-space: nowrap; z-index: 0; pointer-events: none; }',
      'table { width: 100% !important; border-collapse: collapse !important; position: relative; z-index: 1; }',
      'table th, table td { border: 1px solid #dee2e6 !important; padding: 3px 4px !important; text-align: center !important; }',
      `table thead th { background: ${headerColor} !important; color: #fff !important; font-size: 8.5pt; }`,
      'table tbody td { font-size: 8pt; }',
      'table tbody tr:nth-child(even) { background: #f8f9fa !important; }',
      'h1.print-title { text-align: center; margin-bottom: 0.3rem; font-size: 8pt; position: relative; z-index: 1; }'
    ].join('\n');

    const head = win.document.head || win.document.getElementsByTagName('head')[0];
    const styleTag = win.document.createElement('style');
    styleTag.type = 'text/css';
    styleTag.appendChild(win.document.createTextNode(css));
    head.appendChild(styleTag);

    const jQueryInstance = win.jQuery || window.jQuery;
    if (!jQueryInstance) {
      return;
    }

    const $body = jQueryInstance(win.document.body);
    $body.css('padding', '8mm');
    $body.find('h1').remove();
    if (title) {
      $body.prepend(`<h1 class="print-title">${title}</h1>`);
    }

    const $table = $body.find('table').first();
    $table.removeClass('display').addClass('table table-striped table-bordered');
  }

  const SmartPrint = {
    buildButtons: function (options) {
      const opts = $.extend({
        title: '',
        headerColor: '#0d6efd'
      }, options || {});

      return [
        {
          extend: 'excelHtml5',
          text: '<i class="fas fa-file-excel mr-1"></i> Excel',
          className: 'btn btn-success btn-sm'
        },
        {
          extend: 'pdfHtml5',
          text: '<i class="fas fa-file-pdf mr-1"></i> PDF',
          className: 'btn btn-danger btn-sm'
        },
        {
          extend: 'print',
          text: '<i class="fas fa-print mr-1"></i> طباعة',
          title: '',
          className: 'btn btn-info btn-sm smart-print-button d-none',
          attr: {
            'data-smart-print-title': opts.title || '',
            'data-smart-print-header': opts.headerColor || '#0d6efd'
          },
          exportOptions: {
            columns: ':visible'
          },
          smartPrintOptions: opts,
          customize: function (win) {
            applyPrintStyles(win, opts);
          },
          action: function (e, dt, button, config) {
            openModal(dt, this, config.smartPrintOptions || opts);
          },
          init: function (dt, node, config) {
            $(node).data('smartPrintConfig', config);
          }
        }
      ];
    },

    attachTrigger: function (table, triggerSelector, options) {
      ensureModal();
      if (!table) {
        return;
      }

      const $trigger = $(triggerSelector);
      if (!$trigger.length) {
        console.warn('SmartPrint: trigger button not found for selector', triggerSelector);
        return;
      }

      const existing = triggerRegistry.get(table) || {};
      if (existing.selector === triggerSelector) {
        return;
      }

      $trigger.off('click.smartPrint').on('click.smartPrint', (event) => {
        event.preventDefault();
        SmartPrint.trigger(table, options);
      });

      triggerRegistry.set(table, { selector: triggerSelector, options });
    },

    trigger: function (table, options) {
      if (!table) {
        console.warn('SmartPrint: table instance is required for trigger.');
        return;
      }

      const buttonApi = table.button('.smart-print-button');
      if (!buttonApi.length) {
        console.warn('SmartPrint: hidden print button not available.');
        return;
      }

      let opts = options;
      if (!opts) {
        const node = buttonApi.node();
        const $node = $(node);
        const storedConfig = $node.data('smartPrintConfig') || {};
        opts = storedConfig.smartPrintOptions || {
          title: $node.data('smart-print-title') || '',
          headerColor: $node.data('smart-print-header') || '#0d6efd'
        };
      }

      openModal(table, buttonApi, opts || {});
    }
  };

  window.SmartPrint = SmartPrint;
})(window, window.jQuery);
