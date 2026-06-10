<script>
document.addEventListener('DOMContentLoaded', function () {
  const input = document.querySelector('#upload-form input[type="file"]');
  if (!input) return;

  const MAX_SIZE_MB = 5;
  const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

  input.addEventListener('change', function () {
    const file = input.files[0];
    if (!file) return;

    const ext = file.name.split('.').pop().toLowerCase();
    const mime = file.type;

    const allowedExtensions = ['csv', 'xls', 'xlsx'];
    const allowedMimeTypes = [
      'text/csv',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ];

    if (!allowedExtensions.includes(ext) || !allowedMimeTypes.includes(mime)) {
      showNotification('❌ الرجاء اختيار ملف بصيغة CSV أو Excel فقط', 'danger');
      input.value = '';
      return;
    }

    if (file.size > MAX_SIZE_BYTES) {
      showNotification(`❌ حجم الملف كبير جدًا. الحد الأقصى ${MAX_SIZE_MB}MB`, 'danger');
      input.value = '';
      return;
    }

    showNotification('✅ تم اختيار ملف صالح.', 'success');
  });

  function showNotification(message, type = 'info') {
    const el = document.createElement('div');
    el.className = `alert alert-${type} position-fixed top-0 end-0 m-3 shadow`;
    el.style.zIndex = 2000;
    el.innerHTML = `
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(el);
    setTimeout(() => { if (el) el.remove(); }, 5000);
  }
});
</script>
