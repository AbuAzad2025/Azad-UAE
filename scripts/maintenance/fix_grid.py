with open('static/js/pos/grid.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix renderCart to be async and await recalc
old_renderCart = """const renderCart=()=>{
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
  qsa('.qty-minus').forEach(b=>b.addEventListener('click',e=>{const idx=Number(e.target.dataset.idx);if(state.cart[idx]?.qty>1){state.cart[idx].qty--;renderCart();recalc();}else{state.cart.splice(idx,1);renderCart();recalc();}}));
  qsa('.qty-plus').forEach(b=>b.addEventListener('click',e=>{const idx=Number(e.target.dataset.idx);if(state.cart[idx]){state.cart[idx].qty++;renderCart();recalc();}}));
  qsa('.item-remove').forEach(b=>b.addEventListener('click',e=>{const idx=Number(e.target.closest('.item-remove').dataset.idx);state.cart.splice(idx,1);renderCart();recalc();}));
  qsa('.pos-cart-item').forEach(item=>item.addEventListener('click',e=>{const idx=Number(e.currentTarget.dataset.idx);state.selectedLine=idx;renderCart();}));
  recalc();
};"""

new_renderCart = """const renderCart=async ()=>{
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
};"""

if old_renderCart in content:
    content = content.replace(old_renderCart, new_renderCart)
    print('Fixed renderCart')
else:
    print('renderCart not found')

# Fix addToCart to be async
old_addToCart = """const addToCart=(product,qty=1)=>{
  const p=product.product||product;
  const existing=state.cart.find(c=>c.productId===p.id);
  const price=priceForCurrency(toNum(p.price));
  if(existing){existing.qty+=qty;existing.price=price;}
  else{state.cart.push({productId:p.id,name:p.name_ar||p.name,price:price,basePrice:toNum(p.price),qty:qty,discountPercent:0,sku:p.sku||'',barcode:p.barcode||''});}
  renderCart();
};"""

new_addToCart = """const addToCart=async (product,qty=1)=>{
  const p=product.product||product;
  const existing=state.cart.find(c=>c.productId===p.id);
  const price=priceForCurrency(toNum(p.price));
  if(existing){existing.qty+=qty;existing.price=price;}
  else{state.cart.push({productId:p.id,name:p.name_ar||p.name,price:price,basePrice:toNum(p.price),qty:qty,discountPercent:0,sku:p.sku||'',barcode:p.barcode||''});}
  await renderCart();
};"""

if old_addToCart in content:
    content = content.replace(old_addToCart, new_addToCart)
    print('Fixed addToCart')
else:
    print('addToCart not found')

# Fix product card click
old_card = 'if(!p.is_out_of_stock){card.addEventListener(\'click\',()=>{addToCart(p,1);});}'
new_card = 'if(!p.is_out_of_stock){card.addEventListener(\'click\',async ()=>{await addToCart(p,1);});}'

if old_card in content:
    content = content.replace(old_card, new_card)
    print('Fixed product card click')
else:
    print('Product card click not found')

with open('static/js/pos/grid.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
