$(document).ready(function() {
  const $tableEl = $('#salesTable');
  const printOptions = {
    title: 'سجل المبيعات',
    headerColor: '#007A3D'
  };
  let table;
  if ($.fn.DataTable.isDataTable($tableEl)) {
    table = $tableEl.DataTable();
  } else {
    table = $tableEl.DataTable({
      language: { url: "{{ url_for('static', filename='datatables/Arabic.json') }}" },
      order: [[2, 'desc']],
      pageLength: 25,
      responsive: true,
      dom: 'Bfrtip',
      buttons: SmartPrint.buildButtons(printOptions),
      footerCallback: function() {
        const api = this.api();
        const total = api.column(3, { page: 'current' }).data().reduce(function(a, b) {
          const val = parseFloat(b.replace(/[^\d.-]/g, ''));
          return a + (isNaN(val) ? 0 : val);
        }, 0);
        const paid = api.column(4, { page: 'current' }).data().reduce(function(a, b) {
          const val = parseFloat((b.match(/[\d.]+/) || [0])[0]);
          return a + (isNaN(val) ? 0 : val);
        }, 0);
        UI.toast(`إجمالي الصفحة: ${total.toFixed(2)} | مدفوع: ${paid.toFixed(2)}`, 'info', 2000);
      }
    });
  }
  if (!$tableEl.data('smartPrintInit')) {
    SmartPrint.attachTrigger(table, '#printSalesBtn', printOptions);
    $tableEl.data('smartPrintInit', true);
  }
  $('#filterAll').off('click.smartPrint').on('click.smartPrint', function() {
    table.search('').draw();
    $('.btn-group .btn').removeClass('active');
    $(this).addClass('active');
  });
  $('#filterPaid').off('click.smartPrint').on('click.smartPrint', function() {
    table.column(6).search('مدفوع').draw();
    $('.btn-group .btn').removeClass('active');
    $(this).addClass('active');
  });
  $('#filterPartial').off('click.smartPrint').on('click.smartPrint', function() {
    table.column(6).search('جزئي').draw();
    $('.btn-group .btn').removeClass('active');
    $(this).addClass('active');
  });
  $('#filterUnpaid').off('click.smartPrint').on('click.smartPrint', function() {
    table.column(6).search('آجل').draw();
    $('.btn-group .btn').removeClass('active');
    $(this).addClass('active');
  });
});
