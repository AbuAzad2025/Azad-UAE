let currentLineIndex = null;
let currentRequiredQty = 0;
let collectedSerials = {};
function openSerialModal(lineIndex, productName, qty) {
    currentLineIndex = lineIndex;
    currentRequiredQty = parseInt(qty);
    $('#serial_product_name').text(productName);
    $('#serial_quantity_needed').text(currentRequiredQty);
    $('#serial_count').text('0');
    $('#serial_list').empty();
    $('#serial_input').val('');
    if (collectedSerials[lineIndex]) {
        collectedSerials[lineIndex].forEach(sn => addSerialToList(sn));
    }
    $('#serialNumberModal').modal('show');
    setTimeout(() => $('#serial_input').focus(), 500);
}
function addSerialToList(serial) {
    let exists = false;
    $('#serial_list li').each(function() {
        if ($(this).data('serial') === serial) exists = true;
    });
    if (exists) {
        alert('هذا الرقم التسلسلي مضاف بالفعل!');
        return;
    }
    if ($('#serial_list li').length >= currentRequiredQty) {
        alert('لقد أدخلت العدد المطلوب من الأرقام التسلسلية.');
        return;
    }
    const li = $(`
        <li class="list-group-item d-flex justify-content-between align-items-center" data-serial="${serial}">
            ${serial}
            <button type="button" class="btn btn-danger remove-serial">&times;</button>
        </li>
    `);
    $('#serial_list').append(li);
    updateSerialCount();
}
function updateSerialCount() {
    const count = $('#serial_list li').length;
    $('#serial_count').text(count + '/' + currentRequiredQty);
    if (count === currentRequiredQty) {
        $('#save_serials_btn').prop('disabled', false).removeClass('btn-secondary').addClass('btn-success');
    } else {
        $('#save_serials_btn').prop('disabled', true).removeClass('btn-success').addClass('btn-secondary');
    }
    if (count > 0) {
        $('#print_serials_btn').show();
    } else {
        $('#print_serials_btn').hide();
    }
}
$('#add_serial_btn').click(function() {
    const sn = $('#serial_input').val().trim();
    if (sn) {
        addSerialToList(sn);
        $('#serial_input').val('').focus();
    }
});
$('#serial_input').keypress(function(e) {
    if (e.which == 13) {
        e.preventDefault();
        $('#add_serial_btn').click();
    }
});
$('#generate_serial_btn').click(function() {
    const date = new Date().toISOString().slice(0,10).replace(/-/g,'');
    const rand = Math.floor(Math.random() * 10000).toString().padStart(4, '0');
    const sn = `SN-${date}-${rand}`;
    $('#serial_input').val(sn);
    $('#serial_input').focus();
});
$('#print_serials_btn').click(function() {
    const serials = [];
    $('#serial_list li').each(function() {
        serials.push($(this).data('serial'));
    });
    if (serials.length === 0) return;
    const productName = $('#serial_product_name').text();
    const today = new Date();
    const purchaseDate = today.toISOString().slice(0,10);
    const companyName = window._GARAGE_NAME || 'Garage System';
    const companyPhone = window._COMPANY_PHONE || '';
    let printContent = `
        <html>
        <head>
            <style>
                @page { size: 50mm 25mm; margin: 0; }
                body { margin: 0; padding: 1mm; font-family: sans-serif; text-align: center; }
                .label { width: 48mm; height: 23mm; border: 1px dashed #ccc; display: flex; flex-direction: column; justify-content: space-between; align-items: center; page-break-after: always; position: relative; overflow: hidden; }
                .header { font-size: 8px; font-weight: bold; width: 100%; border-bottom: 1px solid #000; padding-bottom: 1px; margin-bottom: 1px; }
                .prod { font-size: 7px; white-space: nowrap; overflow: hidden; max-width: 100%; font-weight: bold; margin: 1px 0; }
                .barcode { height: 18px; width: 90%; }
                .sn { font-size: 9px; font-weight: bold; margin-top: 0; }
                .footer { font-size: 6px; width: 100%; border-top: 1px solid #000; padding-top: 1px; margin-top: 1px; display: flex; justify-content: space-between; align-items: center; }
            </style>
            <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.5/dist/JsBarcode.all.min.js" integrity="sha384-tOUygabpHGzWXpKv3qJM5f9tSgU6p5f4ooCayrNDwzm3/3/CDMzgHMLQZiMMGghV" crossorigin="anonymous"><\/script>
        </head>
        <body>
    `;
    serials.forEach(sn => {
        printContent += `
            <div class="label">
                <div class="header">${companyName}</div>
                <div class="prod">${productName}</div>
                <svg class="barcode"
                    jsbarcode-format="CODE128"
                    jsbarcode-value="${sn}"
                    jsbarcode-textmargin="0"
                    jsbarcode-fontoptions="bold"
                    jsbarcode-height="20"
                    jsbarcode-displayValue="false">
                </svg>
                <div class="sn">${sn}</div>
                <div class="footer">
                    <span>Date: ${purchaseDate}</span>
                    <span>${companyPhone}</span>
                </div>
            </div>
        `;
    });
    printContent += `
        <script>
            JsBarcode(".barcode").init();
            window.onload = function() { window.print(); }
        <\/script>
        </body></html>
    `;
    const frame = document.getElementById('print_frame');
    frame.contentWindow.document.open();
    frame.contentWindow.document.write(printContent);
    frame.contentWindow.document.close();
});
$(document).on('click', '.remove-serial', function() {
    $(this).closest('li').remove();
    updateSerialCount();
});
$('#save_serials_btn').click(function() {
    const serials = [];
    $('#serial_list li').each(function() {
        serials.push($(this).data('serial'));
    });
    collectedSerials[currentLineIndex] = serials;
    renderHiddenSerials();
    $('#serialNumberModal').modal('hide');
    const btn = $(`#serial_btn_${currentLineIndex}`);
    if(btn.length) {
        btn.removeClass('btn-warning').addClass('btn-success').html('<i class="fas fa-check-circle"></i> تم الإدخال');
    }
});
function renderHiddenSerials() {
    const container = $('#serials_container');
    container.empty();
    for (const [lineIdx, serials] of Object.entries(collectedSerials)) {
        serials.forEach(sn => {
            container.append(`<input type="hidden" name="lines[${lineIdx}][serials][]" value="${sn}" aria-label="lines[${lineIdx}][serials][]">`);
        });
    }
}
$(document).ready(function() {
  if (!$('#customer_id').hasClass('select2-hidden-accessible')) {
    $('#customer_id').select2({
      ajax: {
        url: window._API_SEARCH_URL || undefined,
        dataType: 'json',
        delay: 250,
        data: function(params) {
          return { q: params.term, type: 'customers' };
        },
        processResults: function(data) {
          return {
            results: (data.results || []).map(c => ({
              id: c.id,
              text: `${c.name} - ${c.phone}`,
              balance: c.balance
            }))
          };
        },
        cache: true
      },
      language: 'ar',
      dir: 'rtl',
      placeholder: 'ابحث عن زبون...',
      minimumInputLength: 2,
      width: '100%'
    });
  }
  if (window._PRESELECTED_CUSTOMER) {
    (function() {
      const customer = window._PRESELECTED_CUSTOMER;
      const label = customer.name + (customer.phone ? ' - ' + customer.phone : '');
      const option = new Option(label, customer.id, true, true);
      $('#customer_id').append(option).trigger('change');
    })();
  }
});
function validateForm() {
  const lineCount = parseInt($('#line_count').val()) || 0;
  if (lineCount === 0) {
    alert('يجب إضافة منتج واحد على الأقل للفاتورة.\n\nاضغط "إضافة صف" واختر منتجاً.');
    return false;
  }
  let hasProduct = false;
  for (let i = 0; i < lineCount; i++) {
    const productId = $(`select[name="lines[${i}][product_id]"]`).val();
    if (productId) {
      hasProduct = true;
      break;
    }
  }
  if (!hasProduct) {
    alert('يجب اختيار منتج واحد على الأقل.\n\nاختر منتجاً من القائمة المنسدلة.');
    return false;
  } 
  return true;
}
