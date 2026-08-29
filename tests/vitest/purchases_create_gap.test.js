import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

function makeJQuery() {
  const dataStore = new WeakMap();
  function wrap(els) {
    const list = Array.isArray(els) ? els.filter(Boolean) : [els].filter(Boolean);
    const api = {
      length: list.length,
      __els: list,
      each(fn){ list.forEach((el,i)=>fn.call(el,i,el)); return api; },
      find(sel){ const out=[]; list.forEach(el=>out.push(...Array.from(el.querySelectorAll(sel)))); return wrap(out); },
      closest(sel){ return wrap(list.map(el=>el.closest(sel)).filter(Boolean)); },
      append(arg){ list.forEach(el=>{ if(typeof arg==='string') el.insertAdjacentHTML('beforeend',arg); else if(arg&&arg.__els) arg.__els.forEach(c=>el.appendChild(c)); else if(arg instanceof Node) el.appendChild(arg);}); return api; },
      html(v){ if(v===undefined) return list[0]?.innerHTML??''; list.forEach(el=>el.innerHTML=v); return api; },
      text(v){ if(v===undefined) return list[0]?.textContent??''; list.forEach(el=>el.textContent=String(v)); return api; },
      val(v){ if(v===undefined) return list[0]?.value??''; list.forEach(el=>{ if('value' in el) el.value=String(v);}); return api; },
      attr(n,v){ if(v===undefined) return list[0]?.getAttribute(n); list.forEach(el=>el.setAttribute(n,String(v))); return api; },
      data(k,v){ if(v===undefined){ if(!list[0]) return undefined; const s=dataStore.get(list[0]); if(s&&k in s) return s[k]; const camel=k.replace(/-([a-z])/g,(_,c)=>c.toUpperCase()); return list[0].dataset?.[camel];} list.forEach(el=>{ const s=dataStore.get(el)||{}; s[k]=v; dataStore.set(el,s);}); return api; },
      addClass(c){ list.forEach(el=>String(c).split(/\s+/).forEach(x=>x&&el.classList.add(x))); return api; },
      removeClass(c){ list.forEach(el=>String(c).split(/\s+/).forEach(x=>x&&el.classList.remove(x))); return api; },
      css(p,v){ if(v!==undefined){ list.forEach(el=>el.style[p]=v); return api;} return list[0]?.style[p]; },
      show(){ list.forEach(el=>el.style.display='block'); return api; },
      hide(){ list.forEach(el=>el.style.display='none'); return api; },
      remove(){ list.forEach(el=>el.parentNode&&el.parentNode.removeChild(el)); return api; },
      empty(){ list.forEach(el=>el.innerHTML=''); return api; },
      on(...args){
        let names, sel=null, h;
        if(typeof args[0]==='string' && typeof args[1]==='function'){ names=args[0]; h=args[1]; }
        else if(typeof args[1]==='string' && typeof args[2]==='function'){ names=args[0]; sel=args[1]; h=args[2]; }
        else return api;
        names.split(/\s+/).filter(Boolean).forEach(n=>{
          list.forEach(el=>el.addEventListener(n, function(...a){
            if(sel){ const hit=a[0].target instanceof Element && a[0].target.closest(sel); if(!hit) return; }
            h.apply(this,a);
          }));
        });
        return api;
      },
      trigger(e,p){ const ev=new Event(e); ev.params=p; list.forEach(el=>el.dispatchEvent(ev)); return api; },
      focus(){ if(list[0]?.focus) list[0].focus(); return api; },
    };
    const proxy=new Proxy(api,{get(t,prop){ if(prop in t) return t[prop]; if(typeof prop==='symbol') return undefined; if(/^\d+$/.test(prop)) return t.__els[Number(prop)]; if(prop==='then') return undefined; return (...a)=>{ return proxy; }; }});
    return proxy;
  }
  function $(sel){
    if(typeof sel==='string' && sel.trimStart().startsWith('<')){ const tpl=document.createElement('template'); tpl.innerHTML=sel.trim(); return wrap(tpl.content.firstElementChild? [tpl.content.firstElementChild]:[]); }
    if(typeof sel==='string') return wrap(Array.from(document.querySelectorAll(sel)));
    if(sel && sel.__els) return wrap(sel.__els.flat());
    if(sel instanceof Node || sel===document || sel===window){ const a=wrap([sel]); a.ready=(fn)=>{ fn(); return a;}; return a; }
    return wrap([]);
  }
  $.fn={}; $.ajax=vi.fn(); $.ajaxHandlers=[];
  return $;
}

beforeEach(async()=>{
  document.body.innerHTML=`
    <div id="linesContainer"></div>
    <input type="hidden" id="line_count" value="0">
    <select id="currency"><option value="ILS">ILS</option><option value="USD">USD</option></select>
    <input id="exchange_rate" value="1">
    <input id="tax_rate" value="0">
    <input id="freight" value="0"><input id="insurance" value="0"><input id="customs_duty" value="0"><input id="other_landed_cost" value="0">
    <select id="supplier_id"><option value=""></option><option value="5">Sup</option></select>
    <div id="summary_subtotal"></div><div id="summary_tax"></div><div id="summary_landed_cost"></div><div id="summary_total"></div>
    <button id="addLineBtn"></button><form id="purchaseForm"></form>
    <select id="warehouse_id"><option value="1">WH</option></select>
  `;
  window._FX_FALLBACK_BASE='ILS'; window._CURRENCY_SYMBOL='₪'; window._PURCHASE_LABELS={}; window._PURCHASE_CALC_URL='/purchases/api/calculate-totals'; window._PRICES_INCLUDE_VAT=false; window._API_SEARCH_URL='/api/search';
  delete window.SmartSelectors;
  window.toastr=undefined; window.alert=vi.fn();
  global.fetch=vi.fn(async()=>({json:async()=>({success:true,subtotal:0,tax_amount:0,landed_cost:0,total:0})}));
  global.$=makeJQuery(); window.$=global.$;
  vi.resetModules();
  await import('../../static/js/purchases/create.js');
});

afterEach(()=>{ document.body.innerHTML=''; delete global.fetch; delete global.$; delete window.$; delete window.azadEsc; delete window.notify; delete window.addLine; vi.restoreAllMocks(); });

describe('purchases/create gap',()=>{
  it('fallback select2 config without SmartSelectors', async()=>{
    // addLine was called on ready, line_0 exists
    expect(document.getElementById('line_0')).not.toBeNull();
    // The fallback path should have been taken (SmartSelectors missing) – just verify line exists and has product select
    expect(document.querySelector('select.product-select')).not.toBeNull();
  });
  it('removeLine deletes', async()=>{
    expect(document.getElementById('line_0')).not.toBeNull();
    window.removeLine(0);
    expect(document.getElementById('line_0')).toBeNull();
  });
  it('calculateLineTotal math', async()=>{
    const c=document.createElement('div'); c.id='line_9'; c.className='product-line';
    c.innerHTML=`<input class="line-quantity" data-line="9" value="3"><input class="line-cost" data-line="9" value="10"><input class="line-discount" data-line="9" value="10"><input id="line_total_9" data-line="9">`;
    document.getElementById('linesContainer').appendChild(c);
    window.calculateLineTotal(9);
    expect(document.getElementById('line_total_9').value).toBe('27.00');
  });
  it('form submit blocks no lines', async()=>{
    // Clear lines
    document.getElementById('linesContainer').innerHTML='';
    const form=document.getElementById('purchaseForm');
    const evt=new Event('submit',{cancelable:true});
    form.dispatchEvent(evt);
    expect(evt.defaultPrevented).toBe(true);
  });
  it('notify branches', async()=>{
    window.toastr={warning:vi.fn()}; window.notify('warning','hi'); expect(window.toastr.warning).toHaveBeenCalled();
    window.toastr=undefined; window.alert=vi.fn(); window.notify('error','bye'); expect(window.alert).toHaveBeenCalledWith('bye');
  });
});
