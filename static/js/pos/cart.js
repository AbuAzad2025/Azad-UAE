import {
	baseCurrency,
	csrf,
	currencySymbolFor,
	esc,
	fmt,
	newCartKey,
	priceForCurrency,
	pricesIncludeVatMeta,
	qs,
	selectedCurrency,
	state,
	toNum,
} from "./core.js";

const HOLD_KEY = "pos_held_carts";

const updateCartPrices = async () => {
	state.cart.forEach((it) => {
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
		qs("#exchangeRate").value = "1";
		await updateCartPrices();
		return;
	}
	try {
		const r = await fetch(
			`/api/currency-rate/${encodeURIComponent(currency)}/${encodeURIComponent(baseCurrency)}`,
		);
		const data = await r.json();
		if (data.success && data.rate) {
			qs("#exchangeRate").value = Number(data.rate).toFixed(6);
		}
	} catch (_) {}
	await updateCartPrices();
};

const recalc = async () => {
	const taxRate = Math.max(0, Math.min(100, toNum(qs("#taxRate").value)));
	const shipping = Math.max(0, toNum(qs("#shippingCost").value));
	const discountAmount = Math.max(0, toNum(qs("#discountAmount").value));
	let subtotal = 0;
	let discount = 0;
	state.cart.forEach((it) => {
		const lineBase = it.qty * it.price;
		const lineDisc = lineBase * (it.discountPercent / 100);
		subtotal += lineBase - lineDisc;
		discount += lineDisc;
	});
	const quickTax = pricesIncludeVatMeta ? 0 : subtotal * (taxRate / 100);
	const quickTotal = Math.max(0, subtotal + quickTax + shipping - discountAmount);
	qs("#kpiSubtotal").textContent = fmt(subtotal);
	qs("#kpiDiscount").textContent = fmt(discount + discountAmount);
	qs("#kpiTotal").textContent = fmt(quickTotal);
	qs("#kpiCurrency").textContent = currencySymbolFor(selectedCurrency());
	if (state.cart.length > 0) {
		try {
			const r = await fetch("/sales/api/calculate-totals", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"X-CSRFToken": csrf,
				},
				credentials: "same-origin",
				body: JSON.stringify({
					lines: state.cart.map((it) => ({
						quantity: it.qty,
						unit_price: it.price,
						discount_percent: it.discountPercent,
					})),
					discount_amount: discountAmount,
					shipping_cost: shipping,
					tax_rate: taxRate,
					prices_include_vat: pricesIncludeVatMeta,
				}),
			});
			const response = await r.json();
			const data = response?.data ? response.data : response;
			if (response.success) {
				qs("#kpiSubtotal").textContent = fmt(data.subtotal);
				qs("#kpiDiscount").textContent = fmt(data.discount);
				qs("#kpiTotal").textContent = fmt(data.total);
				qs("#kpiCurrency").textContent = currencySymbolFor(selectedCurrency());
				const exactTotals = {
					subtotal: data.subtotal,
					tax: data.tax_amount,
					shipping,
					discountAmount,
					taxRate,
					total: data.total,
					prices_include_vat: data.prices_include_vat,
				};
				if (window.cfdBroadcast) cfdBroadcast.sendCart(state.cart, exactTotals);
				state.lastTotals = exactTotals;
				const chg = qs("#kpiChange");
				if (chg)
					chg.textContent = fmt(Math.max(0, (toNum(qs("#paidAmount").value) || 0) - data.total));
				return exactTotals;
			}
		} catch (_) {}
	}
	const quickTotals = {
		subtotal,
		tax: quickTax,
		shipping,
		discountAmount,
		taxRate,
		total: quickTotal,
		prices_include_vat: pricesIncludeVatMeta,
	};
	if (window.cfdBroadcast) cfdBroadcast.sendCart(state.cart, quickTotals);
	state.lastTotals = quickTotals;
	const chg = qs("#kpiChange");
	if (chg) chg.textContent = fmt(Math.max(0, (toNum(qs("#paidAmount").value) || 0) - quickTotal));
	return quickTotals;
};

let upsellTimer = null;
const renderUpsellMessages = (container, prompts) => {
	if (!container) return;
	container.innerHTML = "";
	const list = Array.isArray(prompts) ? prompts : [];
	list.forEach((p) => {
		const div = document.createElement("div");
		div.className = "pos-upsell-item";
		div.textContent = p?.message || "";
		container.appendChild(div);
	});
	container.classList.toggle("d-none", list.length === 0);
};
const evaluateUpsell = async () => {
	const bar = qs("#upsellBar");
	if (!state.cart.length) {
		renderUpsellMessages(bar, []);
		return;
	}
	try {
		const r = await fetch("/pos/api/promotions/evaluate", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-CSRFToken": csrf,
			},
			credentials: "same-origin",
			body: JSON.stringify({
				customer_id: state.customer?.id || null,
				lines: state.cart.map((it) => ({
					product_id: it.id,
					quantity: it.qty,
					unit_price: it.price,
					discount_percent: it.discountPercent,
				})),
			}),
		});
		const j = await r.json().catch(() => ({}));
		renderUpsellMessages(bar, r.ok && j.success ? j.upsell_prompts : []);
	} catch (_) {
		renderUpsellMessages(bar, []);
	}
};
const scheduleUpsellEval = () => {
	clearTimeout(upsellTimer);
	upsellTimer = setTimeout(() => {
		if (typeof document === "undefined") return;
		void evaluateUpsell();
	}, 400);
};

const renderCart = async () => {
	const body = qs("#cartBody");
	body.innerHTML = "";
	const cnt = qs("#cartCount");
	if (cnt) cnt.textContent = String(state.cart.length);
	if (!state.cart.length) {
		body.innerHTML =
			'<tr id="cartEmptyRow"><td colspan="6" class="text-center text-muted py-4">السلة فارغة — امسح الباركود أو اضغط F2 وابدأ البيع</td></tr>';
		await recalc();
		scheduleUpsellEval();
		return;
	}
	const sym = currencySymbolFor(selectedCurrency());
	state.cart.forEach((it, idx) => {
		const tr = document.createElement("tr");
		const lineTotal = it.qty * it.price * (1 - it.discountPercent / 100);
		const meta =
			(it.sku ? `SKU: ${esc(it.sku)}` : "") + (it.barcode ? ` | ${esc(it.barcode)}` : "");
		tr.innerHTML = `
                <td>
                    <div class="pos-cart-item">
                        <div class="ci-top">
                            <span class="ci-name">${esc(it.name)}</span>
                            <span class="ci-price">${fmt(lineTotal)} ${sym}</span>
                        </div>
                        ${meta ? `<div class="ci-meta">${meta}</div>` : ""}
                        ${it.serial ? `<div class="ci-meta">SN: ${esc(it.serial)}</div>` : ""}
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
	scheduleUpsellEval();
};

const notify = (msg, level = "warning") => {
	window.dispatchEvent(new CustomEvent("pos:alert", { detail: { msg, level } }));
};

const pushLine = async (p, qty, serial) => {
	const existing = !serial ? state.cart.find((x) => x.id === p.id) : null;
	if (existing) {
		existing.qty = Number(existing.qty) + qty;
	} else {
		state.cart.push({
			id: p.id,
			name: p.name,
			sku: p.sku || "",
			barcode: p.barcode || "",
			qty: qty,
			basePrice: toNum(p.price),
			price: priceForCurrency(toNum(p.price)),
			discountPercent: 0,
			...(serial ? { serial } : {}),
		});
	}
	await renderCart();
};

const addToCart = async (p, qty = 1) => {
	state.idemKey = newCartKey();
	if (p.has_serial_number) {
		const serial = (
			window.prompt(`${window.t("أدخل الرقم التسلسلي")}: ${p.name}`) || ""
		).trim();
		if (!serial) {
			notify(window.t("تم إلغاء الإضافة — الرقم التسلسلي مطلوب"), "warning");
			return false;
		}
		await pushLine(p, 1, serial);
		return true;
	}
	await pushLine(p, qty, null);
	return true;
};

const heldCount = () => {
	try {
		return JSON.parse(localStorage.getItem(HOLD_KEY) || "[]").length;
	} catch (_) {
		return 0;
	}
};

export {
	addToCart,
	evaluateUpsell,
	HOLD_KEY,
	heldCount,
	loadRateForCurrency,
	recalc,
	renderCart,
	renderUpsellMessages,
	scheduleUpsellEval,
	updateCartPrices,
};
