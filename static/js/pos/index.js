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
        if (!state.cart.length) {
            body.innerHTML = '<tr id="cartEmptyRow"><td colspan="6" class="text-center text-muted py-4">السلة فارغة</td></tr>';
            await recalc();
            return;
        }
        state.cart.forEach((it, idx) => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>
                    <div><strong>${esc(it.name)}</strong></div>
                    <div class="text-muted small">${it.sku ? ('SKU: '+esc(it.sku)) : ''}${it.barcode ? (' | Barcode: '+esc(it.barcode)) : ''}</div>
                </td>
                <td><input class="form-control form-control-sm text-center" data-k="qty" data-i="${idx}" type="number" step="0.001" min="0.001" value="${it.qty}" aria-label="الكمية"></td>
                <td><input class="form-control form-control-sm text-center" data-k="price" data-i="${idx}" type="number" step="0.01" min="0" value="${it.price}" aria-label="السعر"></td>
                <td><input class="form-control form-control-sm text-center" data-k="disc" data-i="${idx}" type="number" step="0.01" min="0" max="100" value="${it.discountPercent}" aria-label="الخصم"></td>
                <td class="text-center"><strong>${fmt((it.qty * it.price) * (1 - it.discountPercent/100))}</strong></td>
                <td class="text-center">
                    <button class="btn btn-danger" data-k="del" data-i="${idx}" title="حذف"><i class="fas fa-trash"></i></button>
                </td>
            `;
            body.appendChild(tr);
        });
        await recalc();
    };
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
            throw new Error(j.error || 'غير موجود');
        }
        if (!r.ok) {
            const j = await r.json().catch(() => ({}));
            throw new Error(j.error || ('HTTP ' + r.status));
        }
        return r.json();
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
            const box = qs('#customerResults');
            box.innerHTML = '';
            res.forEach(c => {
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
        try {
            const c = await fetchJson('/pos/api/walkin-customer');
            state.customer = c;
            qs('#customerSearch').value = c.text || c.name;
            customerHint();
            qs('#productSearch').focus();
        } catch (err) {
            showAlert(err.message || 'تعذر تحميل عميل نقدي');
        }
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
        try {
            const p = await fetchJson('/pos/api/product?code=' + encodeURIComponent(q) + warehouseParam());
            if (p && p.id) {
                if (p.is_inactive) { showAlert(p.warning || 'المنتج غير نشط.', 'warning'); return; }
                if (p.warning) showAlert(p.warning, 'warning');
                await addToCart(p);
                qs('#productSearch').value = '';
                qs('#productResults').classList.add('d-none');
            }
        } catch (err) {
            if ((state.lastProductResults || []).length) {
                await addToCart(state.lastProductResults[0]);
                qs('#productSearch').value = '';
                qs('#productResults').classList.add('d-none');
            } else {
                showAlert(err.message || 'لم يُعثر على المنتج');
            }
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
        try {
            const res = await fetchJson('/pos/api/products?q=' + encodeURIComponent(q) + warehouseParam());
            renderProductResults(res);
        } catch (err) {
            showAlert(err.message || 'فشل البحث');
        } finally {
            productBusy = false;
            qs('#productLoading').classList.add('d-none');
        }
    };
    qs('#productSearch').addEventListener('input', function(){
        const q = this.value.trim();
        clearTimeout(productTimer);
        productTimer = setTimeout(() => runProductSearch(q), 220);
    });
    qs('#productSearch').addEventListener('keydown', function(e){
        if (e.key === 'Enter') {
            e.preventDefault();
            addFirstOrLookup(this.value.trim());
        }
    });
    qs('#warehouseId').addEventListener('change', function(){
        const q = qs('#productSearch').value.trim();
        if (q) runProductSearch(q);
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
        renderCart();
    });
    qs('#cartBody').addEventListener('click', function(e){
        const btn = e.target.closest('button[data-k="del"]');
        if (!btn) return;
        const idx = Number(btn.getAttribute('data-i'));
        if (!Number.isFinite(idx)) return;
        state.cart.splice(idx, 1);
        renderCart();
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
                throw new Error(j.error || ('HTTP ' + r.status));
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
            checkout(true);
        } else if (e.key === 'Escape') {
            qs('#productSearch').value = '';
            qs('#productResults').classList.add('d-none');
            state.lastProductResults = [];
        }
    });
    customerHint();
    renderCart();
    qs('#productSearch').focus();
    state.barcodeScanner = new BarcodeScanner({
        onScan: async (code) => {
            if (!code || !code.trim()) return;
            try {
                const p = await fetchJson('/pos/api/product?code=' + encodeURIComponent(code.trim()) + warehouseParam());
                if (p && p.id) {
                    if (p.is_inactive) { showAlert(p.warning || 'المنتج غير نشط.', 'warning'); return; }
                    await addToCart(p);
                    qs('#productSearch').value = '';
                    qs('#productResults').classList.add('d-none');
                    showAlert('تمت إضافة ' + p.name, 'success');
                }
            } catch (_) {}
        }
    });
    state.barcodeScanner.start();

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
            if (!r.ok || !j.success) throw new Error(j.error || 'فشل فتح الجلسة');
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
        let reportLoaded = false;
        try {
            const r = await fetch('/pos/api/session/report', { credentials: 'same-origin' });
            const j = await r.json();
            if (j.success && j.session) {
                qs('#closeOpening').textContent = fmt(j.session.opening_balance);
                qs('#closeCashSales').textContent = fmt(j.session.total_cash_sales);
                qs('#closeExpected').textContent = fmt((j.session.opening_balance || 0) + (j.session.total_cash_sales || 0));
                reportLoaded = true;
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
        if (balance === '' || Number.isNaN(Number(qs('#closeSessionBalance').value))) {
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
            if (!r.ok || !j.success) throw new Error(j.error || 'فشل إغلاق الجلسة');
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
    loadSession();
})();
