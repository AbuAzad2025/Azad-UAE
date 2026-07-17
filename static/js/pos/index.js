(function(){
    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    const state = {
        customer: null,
        cart: [],
        lastProductResults: [],
        barcodeScanner: null
    };
    const qs = (s, r=document) => r.querySelector(s);
    const qsa = (s, r=document) => Array.from(r.querySelectorAll(s));
    const fmt = (n) => (Number(n || 0)).toFixed(2);
    const toNum = (v) => {
        const n = Number(v);
        return Number.isFinite(n) ? n : 0;
    };
    const baseCurrency = document.querySelector('meta[name="pos-base-currency"]')?.getAttribute('content') || window._FX_FALLBACK_BASE || '';
    const selectedCurrency = () => qs('#currency').value || baseCurrency;
    const currentRate = () => toNum(qs('#exchangeRate').value) || 1;
    const priceForCurrency = (basePrice) => {
        const rate = currentRate();
        if (selectedCurrency() !== baseCurrency && rate > 0) {
            return toNum(basePrice) / rate;
        }
        return toNum(basePrice);
    };
    const updateCartPrices = async () => {
        state.cart.forEach(it => {
            if (!Number.isFinite(Number(it.basePrice))) {
                it.basePrice = it.price;
            }
            it.price = priceForCurrency(it.basePrice);
        });
        await renderCart();
    };
    const loadRateForCurrency = async () => {
        const currency = selectedCurrency();
        if (currency === baseCurrency) {
            qs('#exchangeRate').value = '1';
            await updateCartPrices();
            return;
        }
        try {
            const r = await fetch(`/api/currency-rate/${encodeURIComponent(currency)}/${encodeURIComponent(baseCurrency)}`);
            const data = await r.json();
            if (data.success && data.rate) {
                qs('#exchangeRate').value = Number(data.rate).toFixed(6);
            }
        } catch (_) {
        }
        await updateCartPrices();
    };
    const esc = (s) => {
        if (s == null) return '';
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    };
    const showAlert = (msg, level='danger') => {
        const el = qs('#posAlert');
        el.className = 'alert alert-' + level;
        el.textContent = msg;
        el.classList.remove('d-none');
        setTimeout(()=>{ el.classList.add('d-none'); }, 5000);
    };
    const showModalAlert = (modalId, msg, level='danger') => {
        const el = qs('#' + modalId + 'Alert');
        if (!el) { showAlert(msg, level); return; }
        el.className = 'alert alert-' + level + ' mb-3';
        el.textContent = msg;
        el.classList.remove('d-none');
        setTimeout(()=>{ el.classList.add('d-none'); }, 6000);
    };
    const hideModalAlert = (modalId) => {
        const el = qs('#' + modalId + 'Alert');
        if (el) el.classList.add('d-none');
    };
    const customerHint = () => {
        const el = qs('#customerSelectedHint');
        if (state.customer) {
            el.textContent = 'العميل المختار: ' + state.customer.text;
            el.className = 'text-success mt-2';
        } else {
            el.textContent = 'لم يتم اختيار عميل بعد';
            el.className = 'text-muted mt-2';
        }
    };
    const pricesIncludeVatMeta = document.querySelector('meta[name="pos-prices-include-vat"]')?.getAttribute('content') === 'true';
    const CURRENCY_SYMBOLS = { USD:'$', ILS:'₪', JOD:'د.أ', EUR:'€', AED:(document.querySelector('meta[name="pos-currency-symbol"]')?.getAttribute('content') || 'د.إ'), SAR:'ر.س', EGP:'ج.م', GBP:'£', KWD:'د.ك', QAR:'ر.ق', OMR:'ر.ع', BHD:'د.ب' };
    const currencySymbolFor = (code) => CURRENCY_SYMBOLS[code] || code;
    const loadOrderTypes = async () => {
        const sel = qs('#orderType');
        if (!sel) return;
        try {
            const r = await fetch('/pos/api/order-types', { credentials: 'same-origin', headers: { 'Accept': 'application/json' } });
            const data = await r.json();
            if (!data.success) return;
            sel.innerHTML = '';
            (data.order_types || []).forEach(ot => {
                const o = document.createElement('option');
                o.value = ot.code;
                o.textContent = ot.display_name;
                sel.appendChild(o);
            });
            if (data.default_code) sel.value = data.default_code;
        } catch (_) {}
    };
    const recalc = async () => {
        const taxRate = Math.max(0, Math.min(100, toNum(qs('#taxRate').value)));
        const shipping = Math.max(0, toNum(qs('#shippingCost').value));
        const discountAmount = Math.max(0, toNum(qs('#discountAmount').value));
        let subtotal = 0;
        let discount = 0;
        state.cart.forEach(it => {
            const lineBase = it.qty * it.price;
            const lineDisc = lineBase * (it.discountPercent / 100);
            subtotal += lineBase - lineDisc;
            discount += lineDisc;
        });
        // Quick local estimate (for responsive UI)
        const quickTax = pricesIncludeVatMeta ? 0 : subtotal * (taxRate / 100);
        const quickTotal = Math.max(0, subtotal + quickTax + shipping - discountAmount);
        qs('#kpiSubtotal').textContent = fmt(subtotal);
        qs('#kpiDiscount').textContent = fmt(discount + discountAmount);
        qs('#kpiTotal').textContent = fmt(quickTotal);
        qs('#kpiCurrency').textContent = currencySymbolFor(selectedCurrency());
        // Backend API for exact calculation (handles prices_include_vat correctly)
        if (state.cart.length > 0) {
            try {
                const r = await fetch('/sales/api/calculate-totals', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrf
                    },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        lines: state.cart.map(it => ({
                            quantity: it.qty,
                            unit_price: it.price,
                            discount_percent: it.discountPercent
                        })),
                        discount_amount: discountAmount,
                        shipping_cost: shipping,
                        tax_rate: taxRate,
                        prices_include_vat: pricesIncludeVatMeta
                    })
                });
                const data = await r.json();
                if (data.success) {
                    qs('#kpiSubtotal').textContent = fmt(data.subtotal);
                    qs('#kpiDiscount').textContent = fmt(data.discount);
                    qs('#kpiTotal').textContent = fmt(data.total);
                    qs('#kpiCurrency').textContent = currencySymbolFor(selectedCurrency());
                    return { subtotal: data.subtotal, tax: data.tax_amount, shipping, discountAmount, taxRate, total: data.total, prices_include_vat: data.prices_include_vat };
                }
            } catch (_) {}
        }
        return { subtotal, tax: quickTax, shipping, discountAmount, taxRate, total: quickTotal, prices_include_vat: pricesIncludeVatMeta };
    };
    const renderCart = async () => {
        const body = qs('#cartBody');
        body.innerHTML = '';
        const cnt = qs('#cartCount');
        if (cnt) cnt.textContent = String(state.cart.length);
        if (!state.cart.length) {
            body.innerHTML = '<tr id="cartEmptyRow"><td colspan="6" class="text-center text-muted py-4">السلة فارغة</td></tr>';
            await recalc();
            return;
        }
        const sym = currencySymbolFor(selectedCurrency());
        state.cart.forEach((it, idx) => {
            const tr = document.createElement('tr');
            const lineTotal = (it.qty * it.price) * (1 - it.discountPercent / 100);
            const meta = (it.sku ? ('SKU: ' + esc(it.sku)) : '') + (it.barcode ? (' | ' + esc(it.barcode)) : '');
            tr.innerHTML = `
                <td>
                    <div class="pos-cart-item">
                        <div class="ci-top">
                            <span class="ci-name">${esc(it.name)}</span>
                            <span class="ci-price">${fmt(lineTotal)} ${sym}</span>
                        </div>
                        ${meta ? `<div class="ci-meta">${meta}</div>` : ''}
                        <div class="ci-controls">
                            <button class="ci-remove" data-k="del" data-i="${idx}" title="حذف">✕</button>
                            <button class="pos-qty-btn" data-act="dec" data-i="${idx}" type="button" aria-label="نقص">−</button>
                            <input class="ci-qty" data-k="qty" data-i="${idx}" type="number" step="0.001" min="0.001" value="${it.qty}" aria-label="الكمية">
                            <button class="pos-qty-btn" data-act="inc" data-i="${idx}" type="button" aria-label="زد">+</button>
                            <input class="ci-price-in" data-k="price" data-i="${idx}" type="number" step="0.01" min="0" value="${it.price}" title="سعر" aria-label="السعر">
                            <input class="ci-disc" data-k="disc" data-i="${idx}" type="number" step="0.01" min="0" max="100" value="${it.discountPercent}" title="خصم %" aria-label="خصم">
                        </div>
                    </div>
                </td>
            `;
            body.appendChild(tr);
        });
        await recalc();
    };

    qs('#cartBody').addEventListener('click', function(e){
        const btn = e.target.closest('button[data-act]');
        if (!btn) return;
        const idx = Number(btn.getAttribute('data-i'));
        if (!Number.isFinite(idx) || !state.cart[idx]) return;
        const act = btn.getAttribute('data-act');
        if (act === 'inc') state.cart[idx].qty = Number(state.cart[idx].qty) + 1;
        if (act === 'dec') state.cart[idx].qty = Math.max(0.001, Number(state.cart[idx].qty) - 1);
        void renderCart();
    });
    const addToCart = async (p) => {
        const existing = state.cart.find(x => x.id === p.id);
        if (existing) {
            existing.qty = Number(existing.qty) + 1;
        } else {
            state.cart.push({
                id: p.id,
                name: p.name,
                sku: p.sku || '',
                barcode: p.barcode || '',
                qty: 1,
                basePrice: toNum(p.price),
                price: priceForCurrency(toNum(p.price)),
                discountPercent: 0
            });
        }
        await renderCart();
    };
    const warehouseParam = () => {
        const w = qs('#warehouseId').value;
        return w ? ('&warehouse_id=' + encodeURIComponent(w)) : '';
    };
    const fetchJson = async (url) => {
        const r = await fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } });
        if (r.status === 404) {
            const j = await r.json().catch(() => ({}));
            return { ok: false, error: j.error || 'غير موجود' };
        }
        if (!r.ok) {
            const j = await r.json().catch(() => ({}));
            return { ok: false, error: j.error || ('HTTP ' + r.status) };
        }
        const data = await r.json();
        return { ok: true, data };
    };
    let customerTimer = null;
    qs('#customerSearch').addEventListener('input', function(){
        const q = this.value.trim();
        clearTimeout(customerTimer);
        customerTimer = setTimeout(async () => {
            if (!q) {
                qs('#customerResults').classList.add('d-none');
                return;
            }
            const res = await fetchJson('/pos/api/customers?q=' + encodeURIComponent(q));
            if (!res.ok) return;
            const box = qs('#customerResults');
            box.innerHTML = '';
            res.data.forEach(c => {
                const a = document.createElement('button');
                a.type = 'button';
                a.className = 'list-group-item list-group-item-action';
                a.textContent = c.text;
                a.addEventListener('click', () => {
                    state.customer = c;
                    qs('#customerSearch').value = c.text;
                    box.classList.add('d-none');
                    customerHint();
                });
                box.appendChild(a);
            });
            box.classList.toggle('d-none', res.length === 0);
        }, 180);
    });
    qs('#clearCustomer').addEventListener('click', () => {
        state.customer = null;
        qs('#customerSearch').value = '';
        qs('#customerResults').classList.add('d-none');
        customerHint();
    });
    qs('#walkinCustomer').addEventListener('click', async () => {
        const res = await fetchJson('/pos/api/walkin-customer');
        if (!res.ok) return showAlert(res.error || 'تعذر تحميل عميل نقدي');
        const c = res.data;
        state.customer = c;
        qs('#customerSearch').value = c.text || c.name;
        customerHint();
        qs('#productSearch').focus();
    });
    let productTimer = null;
    let productBusy = false;
    const renderProductResults = (res) => {
        state.lastProductResults = res || [];
        const box = qs('#productResults');
        box.innerHTML = '';
        (res || []).forEach(p => {
            const a = document.createElement('button');
            a.type = 'button';
            const stockBadge = p.is_out_of_stock
                ? '<span class="badge badge-warning badge-pill ml-1">نفد</span>'
                : `<span class="badge badge-secondary badge-pill ml-1">${fmt(p.stock)}</span>`;
            a.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
            a.innerHTML = `<span>${esc(p.text)}${p.is_inactive ? ' <small class="text-danger">(غير نشط)</small>' : ''}</span><span>${stockBadge} <span class="badge badge-primary badge-pill">${fmt(priceForCurrency(p.price))} ${currencySymbolFor(selectedCurrency())}</span></span>`;
            a.addEventListener('click', async () => {
                if (p.is_inactive) { showAlert('المنتج غير نشط.', 'warning'); return; }
                await addToCart(p);
                qs('#productSearch').value = '';
                box.classList.add('d-none');
                qs('#productSearch').focus();
            });
            box.appendChild(a);
        });
        box.classList.toggle('d-none', !res || res.length === 0);
    };
    const addFirstOrLookup = async (q) => {
        if (!q) return;
        const first = (state.lastProductResults || [])[0];
        if (first && (first.barcode === q || first.sku === q)) {
            await addToCart(first);
            qs('#productSearch').value = '';
            qs('#productResults').classList.add('d-none');
            return;
        }
        const res = await fetchJson('/pos/api/product?code=' + encodeURIComponent(q) + warehouseParam());
        if (!res.ok) {
            if ((state.lastProductResults || []).length) {
                await addToCart(state.lastProductResults[0]);
                qs('#productSearch').value = '';
                qs('#productResults').classList.add('d-none');
            }
            return;
        }
        const p = res.data;
        if (p && p.id) {
            if (p.is_inactive) { showAlert(p.warning || 'المنتج غير نشط.', 'warning'); return; }
            if (p.warning) showAlert(p.warning, 'warning');
            await addToCart(p);
            qs('#productSearch').value = '';
            qs('#productResults').classList.add('d-none');
        } else {
            showAlert(res.error || 'لم يُعثر على المنتج');
        }
    };
    const runProductSearch = async (q) => {
        if (!q) {
            qs('#productResults').classList.add('d-none');
            state.lastProductResults = [];
            qs('#productLoading').classList.add('d-none');
            return;
        }
        if (productBusy) return;
        productBusy = true;
        qs('#productLoading').classList.remove('d-none');
        const res = await fetchJson('/pos/api/products?q=' + encodeURIComponent(q) + warehouseParam());
        if (res.ok) renderProductResults(res.data);
        else showAlert(res.error || 'فشل البحث');
        productBusy = false;
        qs('#productLoading').classList.add('d-none');
    };
    qs('#productSearch').addEventListener('input', function(){
        const q = this.value.trim();
        clearTimeout(productTimer);
        productTimer = setTimeout(() => runProductSearch(q), 220);
    });
    qs('#productSearch').addEventListener('keydown', function(e){
        if (e.key === 'Enter') {
            e.preventDefault();
            void addFirstOrLookup(this.value.trim());
        }
    });
    qs('#warehouseId').addEventListener('change', function(){
        const q = qs('#productSearch').value.trim();
        if (q) void runProductSearch(q);
    });
    qs('#clearProductSearch').addEventListener('click', () => {
        qs('#productSearch').value = '';
        qs('#productResults').classList.add('d-none');
        state.lastProductResults = [];
    });
    qs('#cartBody').addEventListener('input', function(e){
        const t = e.target;
        const idx = Number(t.getAttribute('data-i'));
        const k = t.getAttribute('data-k');
        if (!Number.isFinite(idx) || !state.cart[idx]) return;
        if (k === 'qty') state.cart[idx].qty = Math.max(0.001, toNum(t.value));
        if (k === 'price') {
            state.cart[idx].price = Math.max(0, toNum(t.value));
            state.cart[idx].basePrice = selectedCurrency() !== baseCurrency && currentRate() > 0
                ? state.cart[idx].price * currentRate()
                : state.cart[idx].price;
        }
        if (k === 'disc') state.cart[idx].discountPercent = Math.max(0, Math.min(100, toNum(t.value)));
        void renderCart();
    });
    qs('#cartBody').addEventListener('click', function(e){
        const btn = e.target.closest('button[data-k="del"]');
        if (!btn) return;
        const idx = Number(btn.getAttribute('data-i'));
        if (!Number.isFinite(idx)) return;
        state.cart.splice(idx, 1);
        void renderCart();
    });
    qsa('#taxRate,#shippingCost,#discountAmount').forEach(el => {
        el.addEventListener('input', recalc);
        el.addEventListener('change', recalc);
    });
    qs('#currency').addEventListener('change', loadRateForCurrency);
    qs('#exchangeRate').addEventListener('input', updateCartPrices);
    qs('#exchangeRate').addEventListener('change', updateCartPrices);
    let checkoutBusy = false;
    const checkout = async (autoPrint) => {
        if (checkoutBusy) return;
        if (!state.customer) {
            showAlert('يرجى اختيار العميل أو «نقدي».', 'warning');
            return;
        }
        if (!state.cart.length) {
            showAlert('السلة فارغة.', 'warning');
            return;
        }
        const totals = await recalc();
        const payload = {
            customer_id: state.customer.id,
            quick_customer: !!state.customer.is_walkin,
            warehouse_id: qs('#warehouseId').value || null,
            currency: qs('#currency').value,
            exchange_rate: toNum(qs('#exchangeRate').value) || 1,
            tax_rate: toNum(qs('#taxRate').value) || 0,
            shipping_cost: toNum(qs('#shippingCost').value) || 0,
            discount_amount: toNum(qs('#discountAmount').value) || 0,
            payment_method: qs('#paymentMethod').value || '',
            order_type: qs('#orderType') ? qs('#orderType').value : 'takeaway',
            paid_amount: toNum(qs('#paidAmount').value) || 0,
            payment_currency: qs('#currency').value,
            payment_exchange_rate: toNum(qs('#exchangeRate').value) || 1,
            reference_number: qs('#referenceNumber').value || '',
            notes: qs('#orderNote') ? (qs('#orderNote').value || '') : '',
            lines: state.cart.map(it => ({
                product_id: it.id,
                quantity: it.qty,
                unit_price: it.price,
                discount_percent: it.discountPercent
            }))
        };
        checkoutBusy = true;
        qs('#checkoutBtn').disabled = true;
        qs('#checkoutBtn').classList.add('loading');
        qs('#checkoutPrintBtn').disabled = true;
        qs('#checkoutPrintBtn').classList.add('loading');
        try {
            const r = await fetch('/pos/api/checkout', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': csrf
                },
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            });
            const j = await r.json().catch(()=> ({}));
            if (!r.ok || !j.success) {
                showError(j.error || ('HTTP ' + r.status));
                return;
            }
            qs('#doneSaleNumber').textContent = j.sale_number;
            qs('#doneViewBtn').href = j.view_url;
            qs('#donePrintBtn').href = j.print_url;
            $('#posDoneModal').modal('show');
            if (autoPrint) {
                window.open(j.print_url, '_blank', 'noopener');
            }
            state.cart = [];
            await renderCart();
            qs('#paidAmount').value = 0;
            qs('#paymentMethod').value = '';
            qs('#referenceNumber').value = '';
            if (qs('#orderNote')) qs('#orderNote').value = '';
            if (typeof syncPay === 'function') syncPay();
            if (selectedTable && j.sale_id) {
                try {
                    await fetch('/pos/api/tables/' + selectedTable.id + '/assign', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                        credentials: 'same-origin',
                        body: JSON.stringify({ sale_id: j.sale_id })
                    });
                } catch (_) {}
                selectedTable = null;
                const tb = qs('#posTablesBtn'); if (tb) tb.title = 'إدارة الطاولات';
                const ts = qs('#posTableSelected'); if (ts) ts.textContent = '';
            }
        } catch (err) {
            showAlert(err.message || 'فشل العملية');
        } finally {
            checkoutBusy = false;
            qs('#checkoutBtn').disabled = false;
            qs('#checkoutBtn').classList.remove('loading');
            qs('#checkoutPrintBtn').disabled = false;
            qs('#checkoutPrintBtn').classList.remove('loading');
        }
    };
    qs('#checkoutBtn').addEventListener('click', () => checkout(false));
    qs('#checkoutPrintBtn').addEventListener('click', () => checkout(true));
    document.addEventListener('keydown', (e) => {
        if (e.target.matches('input, textarea, select') && e.key !== 'Escape' && !e.altKey) {
            if (e.key === 'F2' || e.key === 'F4' || e.key === 'F8') {} else return;
        }
        if (e.key === 'F2') {
            e.preventDefault();
            qs('#productSearch').focus();
        } else if (e.key === 'F4') {
            e.preventDefault();
            qs('#customerSearch').focus();
        } else if (e.key === 'F8') {
            e.preventDefault();
            void checkout(true);
        } else if (e.key === 'Escape') {
            qs('#productSearch').value = '';
            qs('#productResults').classList.add('d-none');
            state.lastProductResults = [];
        }
    });
    customerHint();
    void renderCart();
    qs('#productSearch').focus();
    state.barcodeScanner = new BarcodeScanner({
        onScan: async (code) => {
            if (!code || !code.trim()) return;
            const res = await fetchJson('/pos/api/product?code=' + encodeURIComponent(code.trim()) + warehouseParam());
            if (!res.ok) return;
            const p = res.data;
            if (p && p.id) {
                if (p.is_inactive) { showAlert(p.warning || 'المنتج غير نشط.', 'warning'); return; }
                await addToCart(p);
                qs('#productSearch').value = '';
                qs('#productResults').classList.add('d-none');
                showAlert('تمت إضافة ' + p.name, 'success');
            }
        }
    });
    state.barcodeScanner.start();

    /* ---------- Calculator (edits #paidAmount) ---------- */
    const paidEl = qs('#paidAmount');
    const calcGrid = qs('#posCalc');
    const curPaid = () => (paidEl.value === '' || paidEl.value == null) ? '0' : String(paidEl.value);
    if (calcGrid && paidEl) {
        calcGrid.addEventListener('click', (e) => {
            const b = e.target.closest('button[data-act]');
            if (!b) return;
            const act = b.getAttribute('data-act');
            let cur = curPaid();
            if (act === 'digit') { cur = (cur === '0') ? '' : cur; cur += b.getAttribute('data-val'); }
            else if (act === 'dot') { if (!cur.includes('.')) cur += '.'; }
            else if (act === 'back') { cur = cur.length > 1 ? cur.slice(0, -1) : '0'; }
            else if (act === 'clear') { cur = '0'; }
            else if (act === 'add') { cur = (toNum(cur) + toNum(b.getAttribute('data-val'))).toFixed(2).replace(/\.00$/, ''); }
            paidEl.value = cur;
            if (typeof recalc === 'function') recalc();
        });
        paidEl.addEventListener('input', () => { /* keep in sync if typed manually */ });
    }

    /* ---------- Payment method chips ---------- */
    const paySel = qs('#paymentMethod');
    const refField = qs('#refField');
    const syncPay = () => {
        const v = paySel ? paySel.value : '';
        qsa('#posPayMethod .pm').forEach(pm => pm.classList.toggle('active', pm.getAttribute('data-method') === v));
        if (refField) refField.classList.toggle('show', !!v);
    };
    qsa('#posPayMethod .pm').forEach(pm => {
        pm.addEventListener('click', () => {
            if (paySel) paySel.value = pm.getAttribute('data-method');
            syncPay();
        });
    });
    if (paySel) paySel.addEventListener('change', syncPay);
    syncPay();

    /* ---------- Categories + product grid ---------- */
    const loadCategories = async () => {
        const box = qs('#posCategories');
        if (!box) return;
        const res = await fetchJson('/pos/api/categories');
        if (!res.ok) return;
        const cats = res.data;
        if (!cats) return;
        let html = '<div class="pos-cat active" data-cat="">الكل</div>';
        cats.forEach(c => {
            const name = c.name_ar || c.name;
            html += `<div class="pos-cat" data-cat="${c.id}">${esc(name)}</div>`;
        });
        box.innerHTML = html;
        box.querySelectorAll('.pos-cat').forEach(el => {
            el.addEventListener('click', () => {
                box.querySelectorAll('.pos-cat').forEach(x => x.classList.remove('active'));
                el.classList.add('active');
                void loadProducts(el.getAttribute('data-cat'));
            });
        });
    };
    const loadProducts = async (categoryId) => {
        const grid = qs('#posProductGrid');
        if (!grid) return;
        grid.innerHTML = '<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i> جاري التحميل...</div>';
        try {
            const url = '/pos/api/products?per_page=60' + (categoryId ? ('&category_id=' + encodeURIComponent(categoryId)) : '') + warehouseParam();
            const res = await fetchJson(url);
            if (!res.ok || !res.data || !res.data.length) { grid.innerHTML = '<div class="pos-cart-empty">لا توجد منتجات</div>'; return; }
            grid.innerHTML = '';
            res.data.forEach(p => {
                const card = document.createElement('div');
                card.className = 'pos-card' + (p.is_out_of_stock ? ' out' : '');
                const badge = p.is_inactive
                    ? '<span class="badge danger">غير نشط</span>'
                    : (p.is_out_of_stock ? '<span class="badge danger">نفد</span>' : (p.stock <= 5 ? `<span class="badge warn">${fmt(p.stock)}</span>` : ''));
                card.innerHTML = `
                    <div class="icon">📦</div>
                    <div class="name">${esc(p.name)}</div>
                    <div class="meta">
                        <span class="price">${fmt(priceForCurrency(p.price))} ${currencySymbolFor(selectedCurrency())}</span>
                        ${badge}
                    </div>
                `;
                card.addEventListener('click', async () => {
                    if (p.is_inactive) { showAlert('المنتج غير نشط.', 'warning'); return; }
                    await addToCart(p);
                    qs('#productSearch').focus();
                });
                grid.appendChild(card);
            });
        } catch (err) {
            grid.innerHTML = '<div class="pos-cart-empty">تعذر تحميل المنتجات</div>';
        }
    };
    void loadCategories();
    void loadProducts('');

    /* ---------- Ctrl+K focuses product search ---------- */
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
            e.preventDefault();
            qs('#productSearch').focus();
        }
    });

    /* ---------- Runtime profile: restaurant tables + hold (from window.POS_CONFIG) ---------- */
    const POS_CONFIG = window.POS_CONFIG || { enable_tables: false, enable_hold: true };
    const tablesBtn = qs('#posTablesBtn');
    const holdBtn = qs('#posHoldBtn');
    let selectedTable = null;
    if (POS_CONFIG.enable_tables && tablesBtn) tablesBtn.classList.remove('d-none');
    if (POS_CONFIG.enable_hold && holdBtn) holdBtn.classList.remove('d-none');

const loadFloors = async () => {
        const box = qs('#posFloors');
        const grid = qs('#posTablesGrid');
        const res = await fetchJson('/pos/api/floors');
        if (!res.ok) return;
        const floors = res.data;
        if (!floors || !floors.length) {
            box.innerHTML = '<div class="pos-cart-empty">لا توجد أرضيات</div>';
        } else {
            box.innerHTML = floors.map(f => `<div class="pos-cat" data-floor="${f.id}">${esc(f.name_ar || f.name)}</div>`).join('');
            box.querySelectorAll('.pos-cat').forEach(el => el.addEventListener('click', () => {
                box.querySelectorAll('.pos-cat').forEach(x => x.classList.remove('active'));
                el.classList.add('active');
                loadTables(el.getAttribute('data-floor'));
            }));
        }
    };
    const loadTables = async (floorId) => {
        const grid = qs('#posTablesGrid');
        grid.innerHTML = '<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i></div>';
        const res = await fetchJson('/pos/api/floors/' + floorId + '/tables');
        if (!res.ok) { grid.innerHTML = '<div class="pos-cart-empty">تعذر التحميل</div>'; return; }
        const tables = res.data;
        if (!tables) { grid.innerHTML = '<div class="pos-cart-empty">تعذر التحميل</div>'; return; }
        grid.innerHTML = '';
        tables.forEach(t => {
            const occupied = t.status && t.status !== 'free';
            const card = document.createElement('div');
            card.className = 'pos-card' + (occupied ? ' out' : '');
            card.innerHTML = `<div class="icon">🪑</div><div class="name">${esc(t.label)}</div><div class="meta"><span class="price">${esc(t.status || 'free')}</span></div>`;
            card.addEventListener('click', () => {
                selectedTable = { id: t.id, label: t.label };
                const sel = qs('#posTableSelected'); if (sel) sel.textContent = 'الطاولة المحددة: ' + t.label;
                if (tablesBtn) tablesBtn.title = 'الطاولة: ' + t.label;
                if (window.jQuery) $('#posTablesModal').modal('hide');
            });
            grid.appendChild(card);
        });
    };
    if (tablesBtn) {
        tablesBtn.addEventListener('click', loadFloors);
        const clearT = qs('#posTableClear');
        if (clearT) clearT.addEventListener('click', () => {
            selectedTable = null;
            const sel = qs('#posTableSelected'); if (sel) sel.textContent = '';
            if (tablesBtn) tablesBtn.title = 'إدارة الطاولات';
        });
    }

    const HOLD_KEY = 'pos_held_carts';
    const heldCount = () => { try { return (JSON.parse(localStorage.getItem(HOLD_KEY) || '[]')).length; } catch (_) { return 0; } };
    if (holdBtn) {
        holdBtn.addEventListener('click', async () => {
            const list = JSON.parse(localStorage.getItem(HOLD_KEY) || '[]');
            if (!state.cart.length) {
                if (!list.length) { showAlert('لا توجد فواتير معلّقة', 'warning'); return; }
                const last = list.pop();
                localStorage.setItem(HOLD_KEY, JSON.stringify(list));
                state.cart = last.cart || [];
                state.customer = last.customer || null;
                selectedTable = last.table || null;
                if (qs('#orderNote')) qs('#orderNote').value = last.note || '';
                await renderCart();
                customerHint();
                showAlert('تم استئناف الفاتورة المعلّقة', 'success');
                return;
            }
            list.push({
                cart: state.cart,
                customer: state.customer,
                table: selectedTable,
                note: qs('#orderNote') ? (qs('#orderNote').value || '') : '',
                ts: Date.now()
            });
            localStorage.setItem(HOLD_KEY, JSON.stringify(list));
            state.cart = [];
            await renderCart();
            if (qs('#orderNote')) qs('#orderNote').value = '';
            showAlert('تم تعليق الفاتورة (' + heldCount() + ' معلّقة)', 'success');
        });
    }

    async function loadSession() {
        try {
            const r = await fetch('/pos/api/session/current', { credentials: 'same-origin' });
            const j = await r.json();
            const bar = qs('#posSessionBar');
            const required = qs('#posSessionRequired');
            if (j.success && j.session) {
                const s = j.session;
                bar.classList.remove('d-none');
                required.classList.add('d-none');
                qs('#sessionNumber').textContent = s.number;
                qs('#sessionBalance').textContent = fmt(s.opening_balance);
                qs('#sessionTotal').textContent = fmt(s.total_sales);
                qs('#sessionTime').textContent = 'مفتوحة منذ ' + s.duration_minutes + ' دقيقة';
                qs('#closeOpening').textContent = fmt(s.opening_balance);
            } else {
                bar.classList.add('d-none');
                required.classList.remove('d-none');
            }
        } catch (_) {}
    }

    qs('#openSessionBtn').addEventListener('click', () => {
        qs('#openSessionBalance').value = '0';
        qs('#openSessionNotes').value = '';
        $('#openSessionModal').modal('show');
    });

    qs('#openSessionConfirm').addEventListener('click', async () => {
        const balance = toNum(qs('#openSessionBalance').value);
        const notes = qs('#openSessionNotes').value.trim();
        hideModalAlert('openSession');
        qs('#openSessionConfirm').disabled = true;
        try {
            const r = await fetch('/pos/api/session/open', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                credentials: 'same-origin',
                body: JSON.stringify({ opening_balance: balance, notes: notes || undefined })
            });
            const j = await r.json();
            if (!r.ok || !j.success) {
                showModalAlert('openSession', j.error || 'فشل فتح الجلسة', 'danger');
                return;
            }
            $('#openSessionModal').modal('hide');
            await loadSession();
            showAlert('تم فتح الجلسة: ' + j.session.number, 'success');
        } catch (err) {
            showModalAlert('openSession', err.message, 'danger');
        } finally {
            qs('#openSessionConfirm').disabled = false;
        }
    });

    qs('#closeSessionBtn').addEventListener('click', async () => {
        hideModalAlert('closeSession');
        try {
            const r = await fetch('/pos/api/session/report', { credentials: 'same-origin' });
            const j = await r.json();
            if (j.success && j.session) {
                qs('#closeOpening').textContent = fmt(j.session.opening_balance);
                qs('#closeCashSales').textContent = fmt(j.session.total_cash_sales);
                qs('#closeExpected').textContent = fmt((j.session.opening_balance || 0) + (j.session.total_cash_sales || 0));
            }
        } catch (err) {
            showModalAlert('closeSession', 'تعذر تحميل بيانات الجلسة: ' + (err.message || 'خطأ غير معروف'), 'warning');
        }
        qs('#closeSessionBalance').value = '';
        qs('#closeSessionNotes').value = '';
        $('#closeSessionModal').modal('show');
    });

    qs('#closeSessionConfirm').addEventListener('click', async () => {
        const balance = toNum(qs('#closeSessionBalance').value);
        if (Number.isNaN(Number(qs('#closeSessionBalance').value))) {
            showModalAlert('closeSession', 'يرجى إدخال رصيد الإغلاق.', 'warning');
            return;
        }
        const notes = qs('#closeSessionNotes').value.trim();
        hideModalAlert('closeSession');
        qs('#closeSessionConfirm').disabled = true;
        try {
            const r = await fetch('/pos/api/session/close', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                credentials: 'same-origin',
                body: JSON.stringify({ closing_balance: balance, notes: notes || undefined })
            });
            const j = await r.json();
            if (!r.ok || !j.success) {
                showModalAlert('closeSession', j.error || 'فشل إغلاق الجلسة', 'danger');
                return;
            }
            $('#closeSessionModal').modal('hide');
            await loadSession();
            const diff = j.session.difference;
            if (Math.abs(diff) > 0.01) {
                showAlert('تم إغلاق الجلسة. فرق الرصيد: ' + fmt(diff), diff < 0 ? 'danger' : 'warning');
            } else {
                showAlert('تم إغلاق الجلسة بنجاح. الرصيد مطابق.', 'success');
            }
        } catch (err) {
            showModalAlert('closeSession', err.message, 'danger');
        } finally {
            qs('#closeSessionConfirm').disabled = false;
        }
    });

    $('#posDoneModal').on('hidden.bs.modal', function () {
        qs('#productSearch').focus();
    });
    loadOrderTypes();
    void loadSession();
})();
