(function ($) {
  'use strict';

  function optionLabel(cat) {
    return (cat.name_ar || cat.name || '').trim() || cat.name;
  }

  function updateOption($select, cat) {
    const label = optionLabel(cat);
    let $opt = $select.find('option[value="' + cat.id + '"]');
    if ($opt.length) {
      $opt.text(label)
        .attr('data-name', cat.name || '')
        .attr('data-name-ar', cat.name_ar || '')
        .attr('data-description', cat.description || '');
    } else {
      $opt = $('<option></option>')
        .val(String(cat.id))
        .text(label)
        .attr('data-name', cat.name || '')
        .attr('data-name-ar', cat.name_ar || '')
        .attr('data-description', cat.description || '');
      $select.append($opt);
    }
    $select.val(String(cat.id));
  }

  function toggleActions($wrap, categoryId) {
    const enabled = categoryId && String(categoryId) !== '0';
    $wrap.find('.js-category-edit, .js-category-delete').prop('disabled', !enabled);
  }

  function resetModal($modal) {
    $modal.removeData('edit-id');
    $modal.find('.js-category-modal-title').text('إضافة فئة منتجات');
    $modal.find('.js-category-save-label').text('حفظ الفئة');
    $modal.find('#category_name, #category_name_ar, #category_description').val('');
  }

  function fillModalFromOption($modal, $opt) {
    $modal.find('#category_name').val($opt.attr('data-name') || $opt.text());
    $modal.find('#category_name_ar').val($opt.attr('data-name-ar') || '');
    $modal.find('#category_description').val($opt.attr('data-description') || '');
  }

  window.initProductCategoryControls = function (opts) {
    const $select = $(opts.select || '#product_category');
    const $wrap = $(opts.wrap || '.js-category-actions');
    const $modal = $(opts.modal || '#categoryModal');
    const csrf = opts.csrf || $('input[name="csrf_token"]').first().val();

    function selectedId() {
      return $select.val();
    }

    function selectedOption() {
      const id = selectedId();
      if (!id || id === '0') return $();
      return $select.find('option[value="' + id + '"]');
    }

    $select.on('change', function () {
      toggleActions($wrap, selectedId());
    });
    toggleActions($wrap, selectedId());

    $wrap.on('click', '.js-category-add', function () {
      resetModal($modal);
      $modal.modal('show');
    });

    $wrap.on('click', '.js-category-edit', function () {
      const $opt = selectedOption();
      if (!$opt.length) return;
      resetModal($modal);
      $modal.data('edit-id', selectedId());
      $modal.find('.js-category-modal-title').text('تعديل فئة المنتجات');
      $modal.find('.js-category-save-label').text('حفظ التعديلات');
      fillModalFromOption($modal, $opt);
      $modal.modal('show');
    });

    $wrap.on('click', '.js-category-delete', function () {
      const id = selectedId();
      if (!id || id === '0') return;
      const label = selectedOption().text();
      if (!confirm('حذف الفئة «' + label + '»؟\nلن يُسمح إذا كانت مرتبطة بمنتجات.')) return;

      $.ajax({
        url: opts.deleteUrl(id),
        method: 'POST',
        headers: { 'X-CSRFToken': csrf },
        success: function (res) {
          if (!res.success) {
            alert(res.error || 'فشل الحذف');
            return;
          }
          $select.find('option[value="' + id + '"]').remove();
          $select.val('0').trigger('change');
          $('.pc-empty-categories').toggle($select.find('option[value!="0"]').length === 0);
        },
        error: function (xhr) {
          alert((xhr.responseJSON && xhr.responseJSON.error) || 'خطأ في الحذف');
        }
      });
    });

    $modal.on('click', '.js-category-save', function () {
      const name = $('#category_name').val().trim();
      if (!name) {
        alert('أدخل اسم الفئة');
        return;
      }
      const editId = $modal.data('edit-id');
      const payload = {
        name: name,
        name_ar: $('#category_name_ar').val().trim() || null,
        description: $('#category_description').val().trim() || null
      };
      const $btn = $(this).prop('disabled', true);
      $.ajax({
        url: editId ? opts.updateUrl(editId) : opts.createUrl,
        method: 'POST',
        contentType: 'application/json',
        headers: { 'X-CSRFToken': csrf },
        data: JSON.stringify(payload),
        success: function (res) {
          $btn.prop('disabled', false);
          if (!res.success) {
            alert(res.error || 'فشل الحفظ');
            return;
          }
          updateOption($select, res.category);
          $select.trigger('change');
          $('.pc-empty-categories').hide();
          $modal.modal('hide');
          resetModal($modal);
        },
        error: function (xhr) {
          $btn.prop('disabled', false);
          alert((xhr.responseJSON && xhr.responseJSON.error) || 'خطأ في الحفظ');
        }
      });
    });

    $modal.on('hidden.bs.modal', function () {
      resetModal($modal);
    });
  };

  window.initCategoryListControls = function (opts) {
    const $modal = $(opts.modal || '#categoryModal');
    const csrf = opts.csrf || $('input[name="csrf_token"]').first().val();

    $(document).on('click', '.js-category-row-edit', function () {
      const $btn = $(this);
      resetModal($modal);
      $modal.data('edit-id', $btn.data('id'));
      $modal.find('.js-category-modal-title').text('تعديل فئة المنتجات');
      $modal.find('.js-category-save-label').text('حفظ التعديلات');
      $modal.find('#category_name').val($btn.data('name') || '');
      $modal.find('#category_name_ar').val($btn.data('name-ar') || '');
      $modal.find('#category_description').val($btn.data('description') || '');
      $modal.modal('show');
    });

    $(document).on('click', '.js-category-row-delete', function () {
      const $btn = $(this);
      const id = $btn.data('id');
      const label = $btn.data('label') || '';
      if (!confirm('حذف الفئة «' + label + '»؟')) return;
      $.ajax({
        url: opts.deleteUrl(id),
        method: 'POST',
        headers: { 'X-CSRFToken': csrf },
        success: function (res) {
          if (!res.success) {
            alert(res.error || 'فشل الحذف');
            return;
          }
          $btn.closest('tr').fadeOut(200, function () { $(this).remove(); });
        },
        error: function (xhr) {
          alert((xhr.responseJSON && xhr.responseJSON.error) || 'خطأ في الحذف');
        }
      });
    });

    $modal.on('click', '.js-category-save', function () {
      const name = $('#category_name').val().trim();
      if (!name) {
        alert('أدخل اسم الفئة');
        return;
      }
      const editId = $modal.data('edit-id');
      const payload = {
        name: name,
        name_ar: $('#category_name_ar').val().trim() || null,
        description: $('#category_description').val().trim() || null
      };
      const $btn = $(this).prop('disabled', true);
      $.ajax({
        url: editId ? opts.updateUrl(editId) : opts.createUrl,
        method: 'POST',
        contentType: 'application/json',
        headers: { 'X-CSRFToken': csrf },
        data: JSON.stringify(payload),
        success: function () {
          $btn.prop('disabled', false);
          window.location.reload();
        },
        error: function (xhr) {
          $btn.prop('disabled', false);
          alert((xhr.responseJSON && xhr.responseJSON.error) || 'خطأ في الحفظ');
        }
      });
    });
  };
})(jQuery);
