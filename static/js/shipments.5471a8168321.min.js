/* eslint-env browser, jquery */
document.addEventListener('DOMContentLoaded', function () {
  const $ = window.jQuery;
  const fmt2 = n => (Number(n || 0)).toFixed(2);

  const S2_AR = {
    errorLoading: () => 'تعذّر تحميل النتائج',
    inputTooShort: a => `أدخل ${Math.max((a.minimum || 1) - (a.input ? a.input.length : 0), 1)} أحرف على الأقل`,
    inputTooLong: a => `احذف ${a.input.length - a.maximum} أحرف`,
    loadingMore: () => 'جاري تحميل المزيد…',
    maximumSelected: a => `لا يمكنك اختيار أكثر من ${a.maximum} عناصر`,
    noResults: () => 'لا نتائج',
    searching: () => 'جاري البحث…',
    removeAllItems: () => 'إزالة الكل'
  };

  function parseDataParams($el) {
    try { const raw = $el.attr('data-params'); return raw ? JSON.parse(raw) : {}; }
    catch { return {}; }
  }

  function normalizeNum(v) {
    if (v == null) return '';
    let s = String(v).trim();
    const ar = '٠١٢٣٤٥٦٧٨٩';
    s = s.replace(/[٠-٩]/g, d => String(ar.indexOf(d)));
    s = s.replace(/,/g, '.');
    return s;
  }

  function normalizeDateInput(el) {
    if (!el || !el.value) return;
    const v = el.value.trim();
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(v)) {
      const [d, m, y] = v.split('/');
      el.value = `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`;
    }
  }

  function parseNum(v){ v = (v ?? '').toString().trim().replace(',', '.'); const n = parseFloat(v); return isNaN(n)?0:n; }

  function initAjaxSelect2(root) {
    if (!($ && $.fn.select2)) return;

    const itemsWrapEl    = document.getElementById('items-wrapper');
    const partnersWrapEl = document.getElementById('partners-wrapper');

    const resolveUrl = ($el) => {
      const direct = $el.data('url');
      if (direct) return direct;
      const nm = ($el.attr('name') || '');
      if (nm.endsWith('-product_id')   && itemsWrapEl?.dataset.urlProducts)   return itemsWrapEl.dataset.urlProducts;
      if (nm.endsWith('-warehouse_id') && itemsWrapEl?.dataset.urlWarehouses) return itemsWrapEl.dataset.urlWarehouses;
      if (nm.endsWith('-partner_id')   && partnersWrapEl?.dataset.urlPartners) return partnersWrapEl.dataset.urlPartners;
      return null;
    };

    $(root).find('select.select2-ajax').each(function () {
      const $el = $(this);
      const url = resolveUrl($el);
      if (!url) return;
      if ($el.data('select2')) $el.select2('destroy');

      const extra       = parseDataParams($el);
      const placeholder = $el.data('placeholder') || 'اختر...';
      const nm          = ($el.attr('name') || '');
      const newUrl      = $el.data('new-url') || (nm.endsWith('-partner_id') && partnersWrapEl?.dataset.newUrlPartners) || null;

      $el.attr('data-ajax--url', url);

      $el.select2({
        width: '100%',
        theme: 'bootstrap4',
        dir: 'rtl',
        placeholder,
        minimumInputLength: 0,
        ajax: {
          url,
          delay: 150,
          dataType: 'json',
          data: params => Object.assign({ q: (params.term || ''), limit: 20 }, extra || {}),
          processResults: data => {
            const arr = Array.isArray(data) ? data : (Array.isArray(data.results) ? data.results : []);
            return {
              results: arr.map(p => ({
                id: p.id,
                text: p.text || p.name || `ID ${p.id}`,
                name: p.name,
                phone: p.phone || p.phone_number,
                phone_number: p.phone_number,
                identity_number: p.identity_number,
                address: p.address,
                unit_price: p.unit_price
              }))
            };
          },
          cache: false
        },
        templateResult: function (item) {
          if (!item.id) return item.text || item.name || '';
          const phone = item.phone || item.phone_number || '';
          const idn   = item.identity_number || '';
          const name  = item.text || item.name || `ID ${item.id}`;
          return `${name}${phone ? ' — ' + phone : ''}${idn ? ' — ' + idn : ''}`;
        },
        templateSelection: item => (item.text || item.name || 'بدون اسم'),
        language: {
          errorLoading: S2_AR.errorLoading,
          inputTooShort: S2_AR.inputTooShort,
          inputTooLong: S2_AR.inputTooLong,
          loadingMore: S2_AR.loadingMore,
          maximumSelected: S2_AR.maximumSelected,
          noResults: () => newUrl ? `<a href="${newUrl}" target="_blank" class="select2-add-new-partner">+ شريك جديد</a>` : S2_AR.noResults(),
          searching: S2_AR.searching,
          removeAllItems: S2_AR.removeAllItems
        },
        escapeMarkup: m => m,
        dropdownParent: $el.closest('.shipment-partner, .shipment-item, .card')
      });

      const initId   = $el.data('initId') || $el.data('init-id');
      const initText = $el.data('initText') || $el.data('init-text');
      if (initId && (typeof initId === 'number' || String(initId).length)) {
        const has = $el.find(`option[value="${initId}"]`).length > 0;
        if (!has) {
          const opt = new Option(initText || `ID ${initId}`, initId, true, true);
          $el.append(opt);
        }
        $el.val(String(initId)).trigger('change');
      }

      $el.one('select2:open.prefetch', function () {
        const $inp = $('.select2-container--open .select2-search__field');
        if ($inp.length) {
          $inp.val(' ').trigger('input');
          setTimeout(() => { $inp.val('').trigger('input'); }, 50);
        }
      });
    });
  }

  window.initAjaxSelect2 = initAjaxSelect2;

  $(document)
    .off('click.select2AddNew', '.select2-add-new-partner')
    .on('click.select2AddNew', '.select2-add-new-partner', function (e) {
      e.preventDefault();
      const href = $(this).attr('href');
      if (href) window.open(href, '_blank');
    });

  function cloneOptions(fromSelect, toSelect) {
    if (!fromSelect || !toSelect) return;
    const prevVal = toSelect.value;
    toSelect.innerHTML = '';
    Array.from(fromSelect.options).forEach(opt => {
      const o = new Option(opt.text, opt.value, false, false);
      toSelect.add(o);
    });
    if (prevVal) toSelect.value = prevVal;
  }

  function nextIndex(wrapper) {
    const n = Number(wrapper.dataset.index || '0');
    wrapper.dataset.index = String(n + 1);
    return n;
  }

  function htmlToNode(html) {
    const div = document.createElement('div');
    div.innerHTML = html.trim();
    return div.firstElementChild;
  }

  function reindexPartners() {
    const wrap = document.getElementById('partners-wrapper');
    if (!wrap) return;
    const rows = wrap.querySelectorAll('.shipment-partner');
    rows.forEach((row, idx) => {
      row.dataset.index = String(idx);
      const sel = '[id^="partners-"], [name^="partners-"], label[for^="partners-"]';
      row.querySelectorAll(sel).forEach(el => {
        const isLabel = el.tagName.toLowerCase() === 'label';
        const attr = isLabel ? 'for' : (el.name ? 'name' : (el.id ? 'id' : null));
        if (!attr) return;
        const val = el.getAttribute(attr);
        if (!val) return;
        el.setAttribute(attr, val.replace(/partners-\d+-/, `partners-${idx}-`));
      });
    });
    wrap.dataset.index = String(rows.length);
  }

  function recalcItems() {
    const itemsWrap = document.getElementById('items-wrapper');
    const rows = itemsWrap ? itemsWrap.querySelectorAll('.shipment-item') : [];
    let cnt = 0, qty = 0, total = 0;
    rows.forEach(r => {
      const q = parseFloat(r.querySelector('.item-qty')?.value || '0') || 0;
      const c = parseFloat(r.querySelector('.item-cost')?.value || '0') || 0;
      if (q > 0) { cnt += 1; qty += q; total += q * c; }
    });
    const itemsCountEl = document.getElementById('items-count');
    const itemsQtyEl = document.getElementById('items-qty-sum');
    const itemsCostEl = document.getElementById('items-cost-sum');
    if (itemsCountEl) itemsCountEl.textContent = String(cnt);
    if (itemsQtyEl) itemsQtyEl.textContent = String(qty);
    if (itemsCostEl) itemsCostEl.textContent = fmt2(total);
    const fldValueBefore = document.getElementById('value_before') || document.querySelector('[name="value_before"]');
    const fldTotalValue = document.getElementById('total_value') || document.querySelector('[name="total_value"]');
    const fldShipping = document.getElementById('shipping_cost') || document.querySelector('[name="shipping_cost"]');
    const fldCustoms = document.getElementById('customs') || document.querySelector('[name="customs"]');
    const fldVat = document.getElementById('vat') || document.querySelector('[name="vat"]');
    const fldIns = document.getElementById('insurance') || document.querySelector('[name="insurance"]');
    if (fldValueBefore) fldValueBefore.value = fmt2(total);
    const extras = (parseFloat(fldShipping?.value || 0) || 0) + (parseFloat(fldCustoms?.value || 0) || 0) + (parseFloat(fldVat?.value || 0) || 0) + (parseFloat(fldIns?.value || 0) || 0);
    if (fldTotalValue) fldTotalValue.value = fmt2(total + extras);
  }

  function recalcTotalOnExtras() {
    const itemsCostEl = document.getElementById('items-cost-sum');
    const fldValueBefore = document.getElementById('value_before') || document.querySelector('[name="value_before"]');
    const fldTotalValue = document.getElementById('total_value') || document.querySelector('[name="total_value"]');
    const fldShipping = document.getElementById('shipping_cost') || document.querySelector('[name="shipping_cost"]');
    const fldCustoms = document.getElementById('customs') || document.querySelector('[name="customs"]');
    const fldVat = document.getElementById('vat') || document.querySelector('[name="vat"]');
    const fldIns = document.getElementById('insurance') || document.querySelector('[name="insurance"]');
    const itemsTotal = parseFloat(itemsCostEl?.textContent || fldValueBefore?.value || 0) || 0;
    const extras = (parseFloat(fldShipping?.value || 0) || 0) + (parseFloat(fldCustoms?.value || 0) || 0) + (parseFloat(fldVat?.value || 0) || 0) + (parseFloat(fldIns?.value || 0) || 0);
    if (fldTotalValue) fldTotalValue.value = fmt2(itemsTotal + extras);
  }

  function setDefaultWarehouseForRow(row) {
    const fldDest = document.getElementById('destination_id') || document.querySelector('[name="destination_id"]');
    const $dest = $(fldDest);
    const destVal = $dest.val() || fldDest?.value;
    const $w = $(row).find('[name$="-warehouse_id"]');
    if (destVal && $w.length && !$w.val()) {
      const text = $(fldDest).find('option:selected').text() || 'المخزن';
      const opt = new Option(text, destVal, true, true);
      $w.append(opt).trigger('change');
    }
  }

  function addItemRow(opts) {
    const wrapper = document.getElementById('items-wrapper');
    const tpl = document.getElementById('item-row-template');
    if (!(wrapper && tpl)) return;
    const idx = nextIndex(wrapper);
    const node = htmlToNode(tpl.innerHTML.replaceAll('__INDEX__', String(idx)));
    wrapper.appendChild(node);
    const lastRow = wrapper.querySelector('.shipment-item:last-child');
    if (lastRow) {
      initAjaxSelect2(lastRow);
      const pSel = $(lastRow).find('select[name$="-product_id"]');
      if (opts?.product && pSel.length) {
        const opt = new Option(opts.product.text, opts.product.id, true, true);
        pSel.append(opt).trigger('change');
      }
      if (typeof opts?.qty !== 'undefined') lastRow.querySelector('.item-qty').value = opts.qty || '';
      if (typeof opts?.cost !== 'undefined') lastRow.querySelector('.item-cost').value = opts.cost || '';
      setDefaultWarehouseForRow(lastRow);
    }
    recalcItems();
  }

  function addPartnerRow() {
    const wrapper = document.getElementById('partners-wrapper');
    const tpl = document.getElementById('partner-row-template');
    if (!(wrapper && tpl)) return;
    const idx = nextIndex(wrapper);
    const node = htmlToNode(tpl.innerHTML.replaceAll('__INDEX__', String(idx)));
    const firstPartner = wrapper.querySelector('select[name$="-partner_id"]');
    const newPartner = node.querySelector('select[name$="-partner_id"]');
    if (firstPartner && firstPartner.options.length) cloneOptions(firstPartner, newPartner);
    wrapper.appendChild(node);
    const lastRow = wrapper.querySelector('.shipment-partner:last-child');
    if (lastRow) {
      initAjaxSelect2(lastRow);
      $(lastRow).find('select.select2-ajax').val(null).trigger('change');
    }
  }

  const itemsWrap = document.getElementById('items-wrapper');
  const partnersWrap = document.getElementById('partners-wrapper');
  const addItemBtn = document.getElementById('add-item');
  const addPartnerBtn = document.getElementById('add-partner');

  if (addItemBtn) addItemBtn.addEventListener('click', () => addItemRow());
  if (addPartnerBtn) addPartnerBtn.addEventListener('click', () => addPartnerRow());

  if (itemsWrap) {
    itemsWrap.addEventListener('click', e => {
      const btn = e.target.closest('.btn-remove-item');
      if (btn) { btn.closest('.shipment-item')?.remove(); recalcItems(); }
    });
    itemsWrap.addEventListener('input', e => {
      const row = e.target.closest('.shipment-item');
      if (!row) return;
      if (e.target.classList.contains('item-qty') || e.target.classList.contains('item-cost')) {
        const q = parseFloat(row.querySelector('.item-qty')?.value || '0') || 0;
        const c = parseFloat(row.querySelector('.item-cost')?.value || '0') || 0;
        const dv = row.querySelector('.item-declared');
        if (dv) dv.value = fmt2(q * c);
        recalcItems();
      }
    });
  }

  if (partnersWrap) {
    partnersWrap.addEventListener('click', e => {
      const btn = e.target.closest('.btn-remove-partner');
      if (btn) { btn.closest('.shipment-partner')?.remove(); reindexPartners(); updatePartnersPercentGuard(); }
    });
    $(partnersWrap).on('select2:select', 'select[name$="-partner_id"]', function (e) {
      const data = e.params.data || {};
      const row = this.closest('.shipment-partner');
      const setIfEmpty = (sel, v) => { const el = row.querySelector(sel); if (el && !el.value) el.value = v || ''; };
      setIfEmpty('[id$="-identity_number"]', data.identity_number);
      setIfEmpty('[id$="-phone_number"]', data.phone || data.phone_number);
      setIfEmpty('[id$="-address"]', data.address);
      setIfEmpty('[id$="-unit_price_before_tax"]', data.unit_price);
    });
    partnersWrap.addEventListener('input', e=>{
      if (e.target && e.target.name && e.target.name.endsWith('-share_percentage')) updatePartnersPercentGuard();
    });
  }

  const fldShipping = document.getElementById('shipping_cost') || document.querySelector('[name="shipping_cost"]');
  const fldCustoms = document.getElementById('customs') || document.querySelector('[name="customs"]');
  const fldVat = document.getElementById('vat') || document.querySelector('[name="vat"]');
  const fldIns = document.getElementById('insurance') || document.querySelector('[name="insurance"]');
  if (fldShipping) fldShipping.addEventListener('input', recalcTotalOnExtras);
  if (fldCustoms) fldCustoms.addEventListener('input', recalcTotalOnExtras);
  if (fldVat) fldVat.addEventListener('input', recalcTotalOnExtras);
  if (fldIns) fldIns.addEventListener('input', recalcTotalOnExtras);

  const fldDest = document.getElementById('destination_id') || document.querySelector('[name="destination_id"]');
  if (fldDest) $(fldDest).on('change', () => {
    document.querySelectorAll('#items-wrapper .shipment-item').forEach(setDefaultWarehouseForRow);
  });

  const barcodeInput = document.getElementById('barcode-input');
  if (barcodeInput) {
    barcodeInput.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      const code = (barcodeInput.value || '').trim();
      if (!code) return;
      fetch(`/api/products/barcode/${encodeURIComponent(code)}`)
        .then(r => { if (!r.ok) throw new Error('nf'); return r.json(); })
        .then(p => { addItemRow({ product: { id: p.id, text: p.name }, qty: 1, cost: '' }); barcodeInput.value = ''; })
        .catch(() => {});
    });
  }

  function partnersPercentSum(){
    let sum = 0;
    document.querySelectorAll('#partners-wrapper [name$="-share_percentage"]').forEach(el=>{
      sum += parseNum(el.value);
    });
    return sum;
  }

  function updatePartnersPercentGuard(){
    const sum = partnersPercentSum();
    document.querySelectorAll('#partners-wrapper [name$="-share_percentage"]').forEach(el=>{
      if (sum > 100) el.classList.add('is-invalid'); else el.classList.remove('is-invalid');
    });
  }

  initAjaxSelect2(document);
  recalcItems();
  updatePartnersPercentGuard();

  document.getElementById('shipment-form')?.addEventListener('submit', function (e) {
    if (partnersPercentSum() > 100.000001) {
      e.preventDefault();
      updatePartnersPercentGuard();
      alert('مجموع نسب الشركاء لا يجوز أن يتجاوز 100٪.');
      return false;
    }

    reindexPartners();

    document.querySelectorAll('#partners-wrapper .shipment-partner').forEach(function (row) {
      normalizeDateInput(row.querySelector('[name$="-expiry_date"]'));
      ['share_percentage','share_amount','unit_price_before_tax'].forEach(k => {
        const el = row.querySelector(`[name$="-${k}"]`);
        if (el) el.value = normalizeNum(el.value);
      });
      const pid = $(row).find('[name$="-partner_id"]').val();
      if (!pid) row.querySelectorAll('select,input,textarea').forEach(el => { el.disabled = true; });
    });

    document.querySelectorAll('#items-wrapper .shipment-item').forEach(function (row) {
      const pid = $(row).find('[name$="-product_id"]').val();
      const wid = $(row).find('[name$="-warehouse_id"]').val() || ($('#destination_id').val() || document.querySelector('[name="destination_id"]')?.value);
      const qty = row.querySelector('.item-qty')?.value;
      if (!pid || !wid || !qty) {
        row.querySelectorAll('select,input,textarea').forEach(el => { el.disabled = true; });
      }
    });
  });

  const mo = new MutationObserver(muts => {
    for (const m of muts) {
      for (const node of m.addedNodes) {
        if (!(node instanceof HTMLElement)) continue;
        if (node.matches && node.matches('select.select2-ajax')) initAjaxSelect2(node);
        const inner = node.querySelectorAll ? node.querySelectorAll('select.select2-ajax') : [];
        if (inner.length) initAjaxSelect2(node);
      }
    }
  });
  mo.observe(document.body, { childList: true, subtree: true });
});
