/* global jQuery */
(() => {
  'use strict';
  const qs=(s,el=document)=>el.querySelector(s);
  const qsa=(s,el=document)=>Array.from(el.querySelectorAll(s));
  const on=(el,ev,cb)=>el&&el.addEventListener(ev,cb,{passive:false});
  const toNum=v=>{const n=parseFloat((v??'').toString().replace(/[^\d.-]/g,''));return Number.isFinite(n)?n:0;};

  function loadScriptOnce(src){return new Promise(res=>{if(document.querySelector(`script[src="${src}"]`)) return res();const s=document.createElement('script');s.src=src;s.onload=res;document.head.appendChild(s);});}
  function loadCssOnce(href){if(!document.querySelector(`link[href="${href}"]`)){const l=document.createElement('link');l.rel='stylesheet';l.href=href;document.head.appendChild(l);}}
  function loadJQueryOnce(){return new Promise(res=>{if(window.jQuery) return res();const s=document.createElement('script');s.src='https://cdn.jsdelivr.net/npm/jquery@3.6.4/dist/jquery.min.js';s.onload=()=>res();document.head.appendChild(s);});}
  const debounce=(fn, d=200)=>{let t; return (...a)=>{clearTimeout(t);t=setTimeout(()=>fn(...a),d);}};

  async function fetchProductInfo(pid, wid){
    if(!(pid && wid)) return {};
    try{
      const res=await fetch(`/api/products/${pid}/info?warehouse_id=${wid}`, {headers:{'Accept':'application/json'}});
      return await res.json();
    }catch(_){ return {}; }
  }

  // ====== قائمة الفواتير (فلتر) ======
  (function initList(){
    const form = qs('#filterForm');
    if(!form) return;
    on(form,'submit', e=>{
      e.preventDefault();
      const params = new URLSearchParams(new FormData(form));
      const action = form.getAttribute('action') || window.location.pathname;
      window.location = action + '?' + params.toString();
    });
    const resetBtn = form.querySelector('button[type="reset"]');
    if(resetBtn) on(resetBtn,'click',e=>{
      e.preventDefault();
      const action = form.getAttribute('action') || window.location.pathname;
      window.location = action;
    });
  })();

  // ====== إنشاء/تعديل فاتورة ======
  (function initForm(){
    const form = qs('#saleForm');
    if(!form) return;

    // تاريخ افتراضي
    const saleDateEl = form.querySelector('input[name="sale_date"]');
    if(saleDateEl && !saleDateEl.value){
      const pad=n=>n<10?'0'+n:n; const d=new Date();
      saleDateEl.value = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'T'+pad(d.getHours())+':'+pad(d.getMinutes());
    }

    const wantsSelect2 = !!document.querySelector('#saleForm .select2');
    const select2Ready = wantsSelect2
      ? loadJQueryOnce()
          .then(()=>loadCssOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css'))
          .then(()=>loadCssOnce('https://cdn.jsdelivr.net/npm/@ttskch/select2-bootstrap4-theme@1.5.2/dist/select2-bootstrap4.min.css'))
          .then(()=>loadScriptOnce('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js'))
      : Promise.resolve();

    // Sortable
    loadScriptOnce('https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/Sortable.min.js').then(()=>{
      const cont = qs('#saleLines');
      if(cont && window.Sortable){
        new window.Sortable(cont,{handle:'.drag-handle',animation:150,ghostClass:'sortable-ghost'});
      }
    });

    const wrap = qs('#saleLines');
    const addBtn = qs('#addLine');

    function currentMaxIndex(){
      let max=-1;
      qsa('.sale-line',wrap).forEach(row=>{
        if(row.dataset.index && !Number.isNaN(+row.dataset.index)){ max=Math.max(max,+row.dataset.index); return; }
        const any = row.querySelector('input,select,textarea');
        const m = any && (any.name||'').match(/lines-(\d+)-/);
        if(m) max=Math.max(max,+m[1]);
      });
      return Math.max(max,-1);
    }

    function renumberRow(row, i){
      row.dataset.index=i;
      qsa('input,select,textarea',row).forEach(el=>{
        if(el.name) el.name = el.name.replace(/lines-\d+-/,'lines-'+i+'-');
        if(el.id)   el.id   = el.id.replace(/lines-\d+-/,'lines-'+i+'-');
      });
    }

    function clearRow(row){
      qsa('input[type="number"],input[type="text"]',row).forEach(el=>{ el.value=''; });
      qsa('select',row).forEach(s=>{
        s.selectedIndex=0;
        s.dispatchEvent(new Event('change'));
      });
      const badge=row.querySelector('.stock-badge'); if(badge) badge.textContent='';
      row.dataset.priceManual = '';
    }

    function addLine(){
      const rows = qsa('.sale-line',wrap);
      if(!rows.length){ alert('لا يوجد قالب بند لنسخه.'); return; }
      const clone = rows[rows.length-1].cloneNode(true);
      clearRow(clone);
      renumberRow(clone, currentMaxIndex()+1);
      wrap.appendChild(clone);
      bindRow(clone);
      recalc();
    }

    function removeLine(row){
      const rows = qsa('.sale-line',wrap);
      if(rows.length<=1){ alert('يجب ترك بند واحد على الأقل.'); return; }
      row.remove();
      qsa('.sale-line',wrap).forEach((r,i)=>renumberRow(r,i));
      recalc();
    }

    // ----- Select2 helpers -----
    function isSelect2($el){ try{ return !!($el.data('select2') || $el.hasClass('select2-hidden-accessible')); }catch(_){ return false; } }
    function reinitSelect2($el, opts){
      try{
        if(isSelect2($el)) $el.off().select2('destroy');
      }catch(_){}
      $el.empty();
      $el.select2(opts);
    }
    function initAjaxSelect($el, {endpoint, placeholder}){
      const build = () => ({
        theme: 'bootstrap4',
        width: '100%',
        language: 'ar',
        allowClear: !!$el.data('allow-clear'),
        placeholder: placeholder || $el.data('placeholder') || '',
        ajax: {
          delay: 200,
          transport: function (params, success, failure) {
            const url = (typeof endpoint === 'function') ? endpoint() : endpoint;
            params.url = url;
            return jQuery.ajax(params).then(success).catch(failure);
          },
          data: params => ({ q: params.term || '', limit: 50 }),
          // يقبل {results: [...]} أو Array مباشرة
          processResults: data => ({ results: (data && data.results) ? data.results : data })
        }
      });
      if(isSelect2($el)) reinitSelect2($el, build());
      else $el.select2(build());
    }

    function bindRow(row){
      const rm = row.querySelector('.remove-line');
      if(rm) on(rm,'click',()=>removeLine(row));

      const priceInp = row.querySelector('input[name$="-unit_price"]');
      if(priceInp){on(priceInp,'input',()=>{row.dataset.priceManual='1';recalcDebounced();});}

      const nums = qsa('.quantity-input,.price-input,.discount-input,.tax-input',row);
      nums.forEach(el=>{ on(el,'input',recalcDebounced); on(el,'change',recalcDebounced); });

      select2Ready.then(()=>{
        if(!(window.jQuery && window.jQuery.fn && window.jQuery.fn.select2)) return;
        const $ = window.jQuery;
        const $wh = $(row).find('select.warehouse-select');
        const $pd = $(row).find('select.product-select');

        if ($wh.length) {
          initAjaxSelect($wh, {
            endpoint: () => $wh.data('endpoint') || '/api/warehouses',
            placeholder: $wh.data('placeholder') || 'اختر المستودع'
          });
        }

        const initProducts = () => {
          if (!$pd.length) return;
          const wid = $wh.val();
          const endpoint = wid ? `/api/warehouses/${wid}/products` : ($pd.data('endpoint') || '/api/products');
          initAjaxSelect($pd, {
            endpoint: () => endpoint,
            placeholder: $pd.data('placeholder') || 'اختر الصنف'
          });
          $pd.off('select2:select').on('select2:select', async (e) => {
            const data = e.params?.data || {};
            const pid = +$pd.val(); const widNow = +$wh.val();
            if (priceInp && row.dataset.priceManual!=='1') {
              if (typeof data.price!=='undefined') {
                const p = toNum(data.price);
                if(p>0){priceInp.value=p.toFixed(2);recalc();}
              } else {
                const info=await fetchProductInfo(pid,widNow);
                if(info && toNum(info.price)>0){priceInp.value=toNum(info.price).toFixed(2);recalc();}
              }
            }
            updateAvailability(pid,widNow,row);
          });
        };

        initProducts();

        if ($wh.length) {
          $wh.off('change').on('change', () => {
            if ($pd.length) { $pd.val(null).trigger('change'); }
            initProducts();
            updateAvailability(+($pd.val()),+($wh.val()),row);
          });
        }
      });
    }

    async function updateAvailability(pid,wid,row){
      const badge = row.querySelector('.stock-badge');
      if (!badge) return;
      if (!(pid && wid)) { badge.textContent=''; return; }
      const data = await fetchProductInfo(pid,wid);
      const avail = Number.isFinite(+data.available)? +data.available : null;
      badge.textContent = (avail===null?'':'متاح: '+avail);
    }

    function bindAll(){ qsa('.sale-line',wrap).forEach(bindRow); }

    // حسابات
    function recalc(){
      let sub=0, totalDiscount=0;
      qsa('.sale-line',wrap).forEach(row=>{
        const q=toNum(qs('[name$="-quantity"]',row)?.value);
        const p=toNum(qs('[name$="-unit_price"]',row)?.value);
        let d=toNum(qs('[name$="-discount_rate"]',row)?.value); d=Math.max(0,Math.min(100,d));
        const lineTotal = q*p;
        sub += lineTotal*(1-d/100);
        totalDiscount += lineTotal*(d/100);
      });
      let globalTax = toNum(qs('#taxRate')?.value); globalTax=Math.max(0,Math.min(100,globalTax));
      const shipping = toNum(qs('#shippingCost')?.value);
      const taxAmt = sub*(globalTax/100);
      const total = sub + taxAmt + shipping;
      const set=(sel,val)=>{
        const el=qs(sel); if(!el) return;
        const curr = (qs('select[name="currency"]')?.value) || '';
        el.textContent = Number(val).toFixed(2) + (curr?` ${curr}`:'');
      };
      set('#subtotal', sub);
      set('#taxAmount', taxAmt);
      set('#shippingCostDisplay', shipping);
      set('#totalAmount', total);
      set('#discountTotalDisplay', toNum(qs('#discountTotal')?.value));
      const td = qs('#totalDiscount'); if(td){ td.textContent = totalDiscount.toFixed(2); }
    }
    const recalcDebounced = debounce(recalc,150);

    // تهيئة Select2 للعناصر الرأسية
    select2Ready.then(()=>{
      if(!(window.jQuery && window.jQuery.fn && window.jQuery.fn.select2)) return;
      const $ = window.jQuery;
      $('#saleForm select.ajax-select').each(function(){
        const $el = $(this);
        if ($el.closest('.sale-line').length) return;
        const endpoint = $el.data('endpoint');
        if(!endpoint) return;
        initAjaxSelect($el, { endpoint, placeholder: $el.data('placeholder') || '' });
      });
    });

    bindAll();
    if (addBtn) on(addBtn,'click',addLine);
    const taxRate = qs('#taxRate'); if (taxRate) on(taxRate,'input',recalcDebounced);
    const shipping= qs('#shippingCost'); if (shipping) on(shipping,'input',recalcDebounced);
    const currency= qs('select[name="currency"]'); if (currency) on(currency,'change',recalcDebounced);
    recalc();
  })();
})();
