(function () {
  const alertBox = document.getElementById('alertBox');
  const modal = document.getElementById('noteModal');
  const modalBody = document.getElementById('noteModalBody');
  const modalTitle = document.getElementById('noteModalTitle');
  const grid = document.getElementById('notesGrid');
  const btnOpenCreate = document.getElementById('btnOpenCreate');

  function showAlert(message, type) {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = 'alert alert-' + type;
    if (type === 'success') {
      setTimeout(() => {
        alertBox.className = 'alert d-none';
      }, 2000);
    }
  }

  async function loadModalContent(title, url, formMode, noteId = null) {
    modalTitle && (modalTitle.textContent = title);
    const res = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    const html = await res.text();
    modalBody.innerHTML = html;
    $('#noteModal').modal('show');
    wireForm('#noteForm', formMode, noteId);
  }

  function openCreateModal() {
    loadModalContent('ملاحظة جديدة', window.NOTES_ENDPOINTS.createForm, 'create');
  }

  function openEditModal(id) {
    loadModalContent('تعديل الملاحظة', window.NOTES_ENDPOINTS.editForm(id), 'edit', id);
  }

  function cardHTML(note) {
    const badgeClassMap = { URGENT: 'badge-danger', HIGH: 'badge-warning', MEDIUM: 'badge-info' };
    const badgeClass = badgeClassMap[note.priority] || 'badge-secondary';
    return `
      <div class="col-md-6 col-lg-4 mb-3" id="note-card-${note.id}">
        <div class="card note-card h-100 ${note.is_pinned ? 'border-warning' : ''}">
          <div class="card-header d-flex align-items-center justify-content-between">
            <div class="d-flex align-items-center">
              <i class="fas fa-user mr-2 text-muted"></i>
              <strong>${note.author || '-'}</strong>
            </div>
            ${note.priority ? `<span class="badge badge-pill ${badgeClass}">${note.priority}</span>` : ''}
          </div>
          <div class="card-body">
            ${note.is_pinned ? `<div class="mb-2"><i class="fas fa-thumbtack text-warning" title="مثبّت"></i></div>` : ''}
            <p class="mb-3 pre-wrap">${note.content || ''}</p>
            <div class="small text-muted d-flex flex-wrap gap-2">
              <span><i class="fas fa-clock"></i> ${note.created_at || '-'}</span>
            </div>
          </div>
          <div class="card-footer d-flex justify-content-between">
            <div class="btn-group">
              <button class="btn btn-sm btn-outline-primary btn-edit-note" data-id="${note.id}"><i class="fas fa-edit"></i></button>
              <button class="btn btn-sm btn-outline-danger btn-delete-note" data-id="${note.id}"><i class="fas fa-trash"></i></button>
              <button class="btn btn-sm btn-outline-warning btn-pin-note" data-id="${note.id}"><i class="fas fa-thumbtack"></i></button>
            </div>
            <a href="/notes/${note.id}" class="btn btn-sm btn-outline-secondary">تفاصيل</a>
          </div>
        </div>
      </div>`;
  }

  function wireCardActions(scope) {
    scope.querySelectorAll('.btn-edit-note').forEach(btn => {
      btn.addEventListener('click', () => openEditModal(btn.dataset.id));
    });

    scope.querySelectorAll('.btn-delete-note').forEach(btn => {
      btn.addEventListener('click', async () => {
        if (!confirm('تأكيد حذف الملاحظة؟')) return;
        const id = btn.dataset.id;
        const res = await fetch(window.NOTES_ENDPOINTS.delete(id), {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF() }
        });
        const result = await res.json().catch(() => ({ success: false }));
        if (result.success) {
          const card = document.getElementById(`note-card-${id}`);
          if (card) card.remove();
          showAlert('تم حذف الملاحظة.', 'success');
        } else {
          showAlert(result.error || 'فشل الحذف', 'danger');
        }
      });
    });

    scope.querySelectorAll('.btn-pin-note').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.id;
        const res = await fetch(window.NOTES_ENDPOINTS.togglePin(id), {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCSRF() }
        });
        const result = await res.json().catch(() => ({ success: false }));
        if (result.success) {
          showAlert(result.is_pinned ? 'تم تثبيت الملاحظة.' : 'تم إلغاء التثبيت.', 'success');
          if (result.note) {
            const existing = document.getElementById(`note-card-${id}`);
            if (existing) {
              existing.outerHTML = cardHTML(result.note);
              const newOne = document.getElementById(`note-card-${id}`);
              wireCardActions(newOne);
            }
          }
        } else {
          showAlert(result.error || 'فشل العملية', 'danger');
        }
      });
    });
  }

  function getCSRF() {
    const el = document.querySelector('meta[name="csrf-token"]') || document.querySelector('input[name="csrf_token"]');
    return el ? (el.content || el.value) : '';
  }

  function clearErrors(form) {
    form.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    form.querySelectorAll('.invalid-feedback.dynamic').forEach(el => el.remove());
  }

  function addFieldError(form, fieldName, message) {
    const input = form.querySelector(`[name="${fieldName}"]`);
    if (!input) return;
    input.classList.add('is-invalid');
    const feedback = document.createElement('div');
    feedback.className = 'invalid-feedback dynamic';
    feedback.textContent = message;
    (input.parentElement || input).appendChild(feedback);
  }

  function wireForm(selector, mode, id) {
    const form = modalBody.querySelector(selector);
    if (!form) return;

    form.addEventListener('submit', async e => {
      e.preventDefault();
      clearErrors(form);

      const action = form.getAttribute('action') || (mode === 'edit' ? window.NOTES_ENDPOINTS.update(id) : window.NOTES_ENDPOINTS.createForm);
      const res = await fetch(action, {
        method: 'POST',
        body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });

      let result = {};
      try { result = await res.json(); } catch (_) {}

      if (result.success) {
        $('#noteModal').modal('hide');
        showAlert(mode === 'edit' ? 'تم تحديث الملاحظة.' : 'تم إضافة الملاحظة.', 'success');
        const note = result.note;
        if (!grid || !note) return;

        const existingCard = document.getElementById(`note-card-${note.id}`);
        if (existingCard) {
          existingCard.outerHTML = cardHTML(note);
          const newCard = document.getElementById(`note-card-${note.id}`);
          wireCardActions(newCard);
        } else {
          grid.insertAdjacentHTML('afterbegin', cardHTML(note));
          const newCard = document.getElementById(`note-card-${note.id}`);
          wireCardActions(newCard);
        }
      } else if (result.errors) {
        Object.entries(result.errors).forEach(([field, msg]) => {
          addFieldError(form, field, Array.isArray(msg) ? msg[0] : msg);
        });
        showAlert('تحقق من الحقول.', 'danger');
      } else {
        showAlert(result.error || 'حدث خطأ غير متوقع!', 'danger');
      }
    });
  }

  if (btnOpenCreate && modal && modalBody) {
    btnOpenCreate.addEventListener('click', openCreateModal);
  }

  if (grid) {
    wireCardActions(grid);
  }
})();
