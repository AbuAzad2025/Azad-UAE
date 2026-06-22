(function(){
const csrf=document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')||'';
const state={customer:null,cart:[],lastProductResults:[],barcodeScanner:null,selectedCategory:'',numpadBuffer:'',numpadMode:null,selectedLine:null};
const qs=(s,r=document)=>r.querySelector(s);
const qsa=(s,r=document)=>Array.from(r.querySelectorAll(s));
const fmt=(n)=>(Number(n||0)).toFixed(2);
const toNum=(v)=>{const n=Number(v);return Number.isFinite(n)?n:0;};
const baseCurrency=document.querySelector('meta[name="pos-base-currency"]')?.getAttribute('content')||window._FX_FALLBACK_BASE||'';
const pricesIncludeVatMeta=document.querySelector('meta[name="pos-prices-include-vat"]')?.getAttribute('content')==='true';
const currencySymbol=document.querySelector('meta[name="pos-currency-symbol"]')?.getAttribute('content')||baseCurrency;
const esc=(s)=>{if(s==null)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');};
const showAlert=(msg,level='danger')=>{let el=qs('#posAlert');if(!el){el=document.createElement('div');el.id='posAlert';el.className='alert d-none';document.querySelector('.pos-cart-panel').prepend(el);}el.className='alert alert-'+level;el.innerHTML=msg;el.classList.remove('d-none');setTimeout(()=>{el.classList.add('d-none');},5000);};
const selectedCurrency=()=>qs('#currency')?.value||baseCurrency;
const currentRate=()=>toNum(qs('#exchangeRate')?.value)||1;
const priceForCurrency=(basePrice)=>{const rate=currentRate();if(selectedCurrency()!==baseCurrency&&rate>0){return toNum(basePrice)/rate;}return toNum(basePrice);};
const loadRateForCurrency=async()=>{const cur=selectedCurrency();if(cur===baseCurrency){if(qs('#exchangeRate'))qs('#exchangeRate').value='1';await updateCartPrices();return;}try{const r=await fetch('/api/currency-rate/'+encodeURIComponent(cur)+'/'+encodeURIComponent(baseCurrency));const d=await r.json();if(d.success&&d.rate&&qs('#exchangeRate')){qs('#exchangeRate').value=Number(d.rate).toFixed(6);}}catch(_){}await updateCartPrices();};
const updateCartPrices=async ()=>{state.cart.forEach(it=>{if(!Number.isFinite(Number(it.basePrice))){it.basePrice=it.price;}it.price=priceForCurrency(it.basePrice);});await renderCart();};

const recalc=async ()=>{
  const taxRate=Math.max(0,Math.min(100,toNum(qs('#taxRate')?.value)));
  const shipping=Math.max(0,toNum(qs('#shippingCost')?.value));
  const discountAmount=Math.max(0,toNum(qs('#discountAmount')?.value));
  let subtotal=0,lineDiscount=0;
  state.cart.forEach(it=>{const lineBase=it.qty*it.price;const lineDisc=lineBase*(it.discountPercent/100);subtotal+=lineBase-lineDisc;lineDiscount+=lineDisc;});
  const quickTax=pricesIncludeVatMeta?0:subtotal*(taxRate/100);
  const quickTotal=Math.max(0,subtotal+quickTax+shipping-discountAmount);
  qs('#kpiSubtotal').textContent=fmt(subtotal);
  qs('#kpiTax').textContent=fmt(quickTax);
  qs('#kpiDiscount').textContent=fmt(lineDiscount+discountAmount);
  qs('#kpiShipping').textContent=fmt(shipping);
  qs('#kpiTotal').textContent=fmt(quickTotal);
  qs('#kpiCurrency').textContent=currencySymbol;
  const taxRow=qs('#taxRow');if(taxRow)taxRow.style.display=taxRate>0?'':'none';
  if(state.cart.length>0){qs('#cartEmpty')?.classList.add('d-none');qs('#cartItems')?.classList.remove('d-none');}
  else{qs('#cartEmpty')?.classList.remove('d-none');qs('#cartItems')?.classList.add('d-none');}
  if(state.cart.length>0){
    try{
      const r=await fetch('/sales/api/calculate-totals',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},credentials:'same-origin',body:JSON.stringify({lines:state.cart.map(it=>({quantity:it.qty,unit_price:it.price,discount_percent:it.discountPercent})),discount_amount:discountAmount,shipping_cost:shipping,tax_rate:taxRate,prices_include_vat:pricesIncludeVatMeta})});
      const data=await r.json();
      if(data.success){
        qs('#kpiSubtotal').textContent=fmt(data.subtotal);
        qs('#kpiTax').textContent=fmt(data.tax_amount);
        qs('#kpiDiscount').textContent=fmt(data.discount);
        qs('#kpiTotal').textContent=fmt(data.total);
        qs('#kpiCurrency').textContent=currencySymbol;
        return{subtotal:data.subtotal,tax:data.tax_amount,shipping,discountAmount,lineDiscount,taxRate,total:data.total,prices_include_vat:data.prices_include_vat};
      }
    }catch(_){}
  }
  return{subtotal,tax:quickTax,shipping,discountAmount,lineDiscount,taxRate,total:quickTotal,prices_include_vat:pricesIncludeVatMeta};
};

const renderCart=async ()=>{
  const container=qs('#cartItems');
  container.innerHTML='';
  state.cart.forEach((it,idx)=>{
    const div=document.createElement('div');
    div.className='pos-cart-item'+(state.selectedLine===idx?' selected':'');
    div.dataset.idx=idx;
    const lineTotal=it.qty*it.price*(1-(it.discountPercent||0)/100);
    div.innerHTML=`<div class="item-info"><div class="item-name">${esc(it.name)}</div><div class="item-price">${fmt(it.price)} x ${it.qty}${it.discountPercent?' ('+it.discountPercent+'% خصم)':''}</div></div><div class="item-qty"><button class="qty-minus" data-idx="${idx}">-</button><span>${it.qty}</span><button class="qty-plus" data-idx="${idx}">+</button></div><div class="item-total">${fmt(lineTotal)}</div><div class="item-remove" data-idx="${idx}"><i class="fas fa-times"></i></div>`;
    container.appendChild(div);
  });
  qsa('.qty-minus').forEach(b=>b.addEventListener('click',async e=>{const idx=Number(e.target.dataset.idx);if(state.cart[idx]?.qty>1){state.cart[idx].qty--;await renderCart();await recalc();}else{state.cart.splice(idx,1);await renderCart();await recalc();}}));
  qsa('.qty-plus').forEach(b=>b.addEventListener('click',async e=>{const idx=Number(e.target.dataset.idx);if(state.cart[idx]){state.cart[idx].qty++;await renderCart();await recalc();}}));
  qsa('.item-remove').forEach(b=>b.addEventListener('click',async e=>{const idx=Number(e.target.closest('.item-remove').dataset.idx);state.cart.splice(idx,1);await renderCart();await recalc();}));
  qsa('.pos-cart-item').forEach(item=>item.addEventListener('click',e=>{const idx=Number(e.currentTarget.dataset.idx);state.selectedLine=idx;renderCart();}));
  await recalc();
};

const addToCart=async (product,qty=1)=>{
  const p=product.product||product;
  const existing=state.cart.find(c=>c.productId===p.id);
  const price=priceForCurrency(toNum(p.price));
  if(existing){existing.qty+=qty;existing.price=price;}
  else{state.cart.push({productId:p.id,name:p.name_ar||p.name,price:price,basePrice:toNum(p.price),qty:qty,discountPercent:0,sku:p.sku||'',barcode:p.barcode||''});}
  await renderCart();
};

const renderProductGrid=(products)=>{
  const grid=qs('#productGrid');
  grid.innerHTML='';
  products.forEach(p=>{
    const card=document.createElement('div');
    card.className='pos-product-card'+(p.is_out_of_stock?' out-of-stock':'');
    card.dataset.id=p.id;
    const img=p.image_url?`<img src="${esc(p.image_url)}" class="prod-img" alt="">`:`<div class="prod-img d-flex align-items-center justify-content-center text-muted"><i class="fas fa-box fa-2x"></i></div>`;
    card.innerHTML=`${img}<div class="prod-name">${esc(p.name_ar||p.name)}</div><div class="prod-price">${fmt(p.price)}</div><div class="prod-stock ${p.stock<=0?'out':p.stock<=5?'low':''}">${p.stock_label||''}</div>`;
    if(!p.is_out_of_stock){card.addEventListener('click',async ()=>{await addToCart(p,1);});}
    grid.appendChild(card);
  });
};

const loadCategories=async()=>{
  try{
    const r=await fetch('/pos/api/categories');
    const data=await r.json();
    const list=qs('#categoryList');
    list.innerHTML='';
    data.forEach(cat=>{
      const div=document.createElement('div');
      div.className='cat-item';
      div.dataset.catId=cat.id;
      div.innerHTML=`<i class="fas fa-tag mr-2"></i>${esc(cat.name_ar||cat.name)}`;
      div.addEventListener('click',()=>{qsa('.cat-item').forEach(c=>c.classList.remove('active'));div.classList.add('active');state.selectedCategory=cat.id;loadProducts();});
      list.appendChild(div);
    });
  }catch(_){}
};

const loadProducts=async(q='')=>{
  qs('#productLoading')?.classList.remove('d-none');
  try{
    const params=new URLSearchParams();
    if(q)params.append('q',q);
    if(state.selectedCategory)params.append('category_id',state.selectedCategory);
    const wid=qs('#warehouseId')?.value;if(wid)params.append('warehouse_id',wid);
    params.append('per_page','40');
    const r=await fetch('/pos/api/products?'+params.toString());
    const data=await r.json();
    state.lastProductResults=data;
    if(data.length>0){renderProductGrid(data);qs('#productResults')?.classList.add('d-none');}
    else{qs('#productGrid').innerHTML='<div class="text-center text-muted py-5 w-100">لا توجد منتجات</div>';}
  }catch(_){}
  qs('#productLoading')?.classList.add('d-none');
};

const handleNumpad=(key)=>{
  if(key==='del'){state.numpadBuffer=state.numpadBuffer.slice(0,-1);return;}
  if(key==='Enter'&&state.numpadMode&&state.numpadBuffer&&state.selectedLine!==null){
    const val=toNum(state.numpadBuffer);
    const line=state.cart[state.selectedLine];
    if(!line)return;
    if(state.numpadMode==='qty'&&val>0){line.qty=val;}
    else if(state.numpadMode==='disc'&&val>=0&&val<=100){line.discountPercent=val;}
    else if(state.numpadMode==='price'&&val>=0){line.basePrice=val;line.price=priceForCurrency(val);}
    state.numpadBuffer='';state.numpadMode=null;renderCart();recalc();return;
  }
  if(key==='qty'||key==='disc'||key==='price'){
    if(state.selectedLine===null){showAlert('اختر منتجاً من السلة أولاً','warning');return;}
    state.numpadMode=key;state.numpadBuffer='';
    const labels={qty:'الكمية',disc:'نسبة الخصم',price:'السعر'};
    showAlert('أدخل '+labels[key]+' باستخدام لوحة الأرقام ثم اضغط Enter','info');
    return;
  }
  if(key.match(/^[0-9.]$/)&&state.numpadMode){state.numpadBuffer+=key;return;}
};

const initSession=()=>{
  fetch('/pos/api/session/current').then(r=>r.json()).then(d=>{
    if(d.success&&d.session){
      qs('#posSessionBar').classList.remove('d-none');qs('#posSessionRequired').classList.add('d-none');
      qs('#sessionNumber').textContent=d.session.number;
      qs('#sessionBalance').textContent=fmt(d.session.opening_balance);
      qs('#sessionTotal').textContent=fmt(d.session.total_sales);
    }else{
      qs('#posSessionBar').classList.add('d-none');qs('#posSessionRequired').classList.remove('d-none');
    }
  }).catch(()=>{});
};

const customerHint=()=>{
  const el=qs('#customerSelectedHint');
  if(state.customer){el.textContent=state.customer.text||state.customer.name;el.className='text-success';}
  else{el.textContent='لم يتم اختيار عميل';el.className='text-muted';}
};

const searchCustomers=async(q)=>{
  if(!q){qs('#customerResults')?.classList.add('d-none');return;}
  try{
    const r=await fetch('/pos/api/customers?q='+encodeURIComponent(q));
    const data=await r.json();
    const list=qs('#customerResults');
    list.innerHTML='';
    data.forEach(c=>{
      const item=document.createElement('a');
      item.className='list-group-item list-group-item-action';
      item.href='#';
      item.textContent=c.text;
      item.addEventListener('click',e=>{e.preventDefault();state.customer=c;customerHint();qs('#customerResults').classList.add('d-none');});
      list.appendChild(item);
    });
    list.classList.remove('d-none');
  }catch(_){}
};

const doCheckout=async(print=false)=>{
  if(state.cart.length===0){showAlert('السلة فارغة','warning');return;}
  if(!state.customer){try{const r=await fetch('/pos/api/walkin-customer');const d=await r.json();if(d.success)state.customer=d;}catch(e){showAlert('تعذر اختيار عميل نقدي');return;}}
  const totals=recalc();
  const lines=state.cart.map(it=>({product_id:it.productId,quantity:it.qty,unit_price:it.price,discount_percent:it.discountPercent||0}));
  const body={
    customer_id:state.customer?.id,quick_customer:true,
    warehouse_id:qs('#warehouseId')?.value||null,
    currency:selectedCurrency(),
    exchange_rate:currentRate()||1,
    tax_rate:toNum(qs('#taxRate')?.value)||0,
    shipping_cost:toNum(qs('#shippingCost')?.value)||0,
    discount_amount:toNum(qs('#discountAmount')?.value)||0,
    payment_method:qs('#paymentMethod')?.value||'',
    paid_amount:toNum(qs('#paidAmount')?.value)||0,
    payment_currency:selectedCurrency(),
    payment_exchange_rate:currentRate()||1,
    reference_number:qs('#referenceNumber')?.value||'',
    lines:lines
  };
  try{
    const r=await fetch('/pos/api/checkout',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify(body)});
    const d=await r.json();
    if(d.success){
      qs('#doneSaleNumber').textContent=d.sale_number;
      qs('#doneViewBtn').href=d.view_url;
      qs('#donePrintBtn').href=d.print_url;
      $('#posDoneModal').modal('show');
      state.cart=[];renderCart();
      if(print){window.open(d.print_url,'_blank');}
    }else{showAlert(d.error||'فشل حفظ الفاتورة');}
  }catch(_){showAlert('فشل الاتصال بالخادم');}
};

document.addEventListener('DOMContentLoaded',()=>{
  loadCategories();
  loadProducts();
  initSession();

  qs('#productSearch').addEventListener('input',(e)=>{const q=e.target.value.trim();setTimeout(()=>loadProducts(q||''),150);});
  qs('#productSearch').addEventListener('keydown',(e)=>{if(e.key==='Enter'){e.preventDefault();const q=e.target.value.trim();if(q)loadProducts(q);}});

  const custSearch=qs('#customerSearch')||qs('#customerSelectedHint');
  if(custSearch&&custSearch.id==='customerSearch'){
    let custTimer;
    custSearch.addEventListener('input',(e)=>{clearTimeout(custTimer);const q=e.target.value.trim();custTimer=setTimeout(()=>searchCustomers(q),200);});
  }
  qs('#walkinCustomer')?.addEventListener('click',()=>{fetch('/pos/api/walkin-customer').then(r=>r.json()).then(d=>{if(d.success){state.customer=d;customerHint();}}).catch(()=>{});});
  qs('#clearCustomer')?.addEventListener('click',()=>{state.customer=null;customerHint();});

  qsa('.pos-numpad button').forEach(b=>b.addEventListener('click',(e)=>{handleNumpad(e.currentTarget.dataset.key);}));

  qs('#checkoutBtn').addEventListener('click',()=>doCheckout(false));
  qs('#checkoutPrintBtn')?.addEventListener('click',()=>doCheckout(true));
  qs('#clearCartBtn')?.addEventListener('click',()=>{state.cart=[];renderCart();});

  qsa('#taxRate,#shippingCost,#discountAmount,#paidAmount,#paymentMethod,#warehouseId').forEach(el=>{if(el)el.addEventListener('change',recalc);if(el)el.addEventListener('input',recalc);});
  qs('#currency')?.addEventListener('change',loadRateForCurrency);
  qs('#exchangeRate')?.addEventListener('input',updateCartPrices);
  qs('#exchangeRate')?.addEventListener('change',updateCartPrices);
  qs('#warehouseId')?.addEventListener('change',()=>{const q=qs('#productSearch')?.value?.trim();if(q)loadProducts(q);});

  qs('#openSessionBtn').addEventListener('click',()=>{$('#openSessionModal').modal('show');});
  qs('#openSessionConfirm').addEventListener('click',()=>{const bal=toNum(qs('#openSessionBalance').value);fetch('/pos/api/session/open',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({opening_balance:bal,notes:qs('#openSessionNotes')?.value})}).then(r=>r.json()).then(d=>{if(d.success){$('#openSessionModal').modal('hide');initSession();}else{showAlert(d.error||'فشل فتح الجلسة');}}).catch(()=>{});});
  qs('#closeSessionBtn').addEventListener('click',()=>{fetch('/pos/api/session/report').then(r=>r.json()).then(d=>{if(d.success&&d.session){qs('#closeOpening').textContent=fmt(d.session.opening_balance);qs('#closeCashSales').textContent=fmt(d.session.total_cash_sales);qs('#closeExpected').textContent=fmt(d.session.expected_balance||0);$('#closeSessionModal').modal('show');}}).catch(()=>{});});
  qs('#closeSessionConfirm').addEventListener('click',()=>{const bal=toNum(qs('#closeSessionBalance').value);fetch('/pos/api/session/close',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify({closing_balance:bal,notes:qs('#closeSessionNotes')?.value})}).then(r=>r.json()).then(d=>{if(d.success){$('#closeSessionModal').modal('hide');initSession();}else{showAlert(d.error||'فشل إغلاق الجلسة');}}).catch(()=>{});});

  if(window.BarcodeScanner){
    state.barcodeScanner=new BarcodeScanner({onScan:(code)=>{qs('#productSearch').value=code;fetch('/pos/api/product?code='+encodeURIComponent(code)).then(r=>r.json()).then(d=>{if(d.success!==false){addToCart(d,1);qs('#productSearch').value='';}else{showAlert(d.error||'المنتج غير موجود');}}).catch(()=>{});},minLength:3});
  }

  document.addEventListener('keydown',(e)=>{
    if(e.target.matches('input,textarea,select')&&e.key!=='Escape'&&e.key!=='Enter')return;
    if(e.key==='Enter'&&state.numpadMode){handleNumpad('Enter');return;}
    if(e.key==='F2'){e.preventDefault();qs('#productSearch')?.focus();}
    if(e.key==='F4'){qs('#customerSearch')?.focus();}
    if(e.key==='F8'){e.preventDefault();doCheckout(true);}
    if(e.key==='Escape'){state.numpadBuffer='';state.numpadMode=null;}
  });
});
})();
