(() => {
	const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
	const state = {
		customer: null,
		cart: [],
		lastProductResults: [],
		barcodeScanner: null,
	};
	// One idempotency key per cart lifecycle — bumped on every cart mutation
	// and after each successful checkout, so retries/SW replays of the SAME
	// cart dedupe server-side while a changed cart always posts fresh.
	const newCartKey = () =>
		window.crypto && crypto.randomUUID
			? crypto.randomUUID()
			: `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;
	state.idemKey = newCartKey();
	const qs = (s, r = document) => r.querySelector(s);
	const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));
	const fmt = (n) => Number(n || 0).toFixed(2);
	const toNum = (v) => {
		const n = Number(v);
		return Number.isFinite(n) ? n : 0;
	};
	const baseCurrency =
		document.querySelector('meta[name="pos-base-currency"]')?.getAttribute("content") ||
		window._FX_FALLBACK_BASE ||
		"";
	const selectedCurrency = () => qs("#currency").value || baseCurrency;
	const currentRate = () => toNum(qs("#exchangeRate").value) || 1;
	const priceForCurrency = (basePrice) => {
		const rate = currentRate();
		if (selectedCurrency() !== baseCurrency && rate > 0) {
			return toNum(basePrice) / rate;
		}
		return toNum(basePrice);
	};
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
	const esc = (s) => {
		if (s == null) return "";
		return String(s)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	};
	const showAlert = (msg, level = "danger") => {
		const el = qs("#posAlert");
		el.className = `alert alert-${level}`;
		el.textContent = msg;
		el.classList.remove("d-none");
		setTimeout(() => {
			el.classList.add("d-none");
		}, 5000);
	};
	const showModalAlert = (modalId, msg, level = "danger") => {
		const el = qs(`#${modalId}Alert`);
		if (!el) {
			showAlert(msg, level);
			return;
		}
		el.className = `alert alert-${level} mb-3`;
		el.textContent = msg;
		el.classList.remove("d-none");
		setTimeout(() => {
			el.classList.add("d-none");
		}, 6000);
	};
	const hideModalAlert = (modalId) => {
		const el = qs(`#${modalId}Alert`);
		if (el) el.classList.add("d-none");
	};
	const customerHint = () => {
		const el = qs("#customerSelectedHint");
		if (state.customer) {
			el.textContent = `العميل المختار: ${state.customer.text}`;
			el.className = "text-success mt-2";
		} else {
			el.textContent = "لم يتم اختيار عميل بعد";
			el.className = "text-muted mt-2";
		}
	};
	const pricesIncludeVatMeta =
		document.querySelector('meta[name="pos-prices-include-vat"]')?.getAttribute("content") ===
		"true";
	const CURRENCY_SYMBOLS = {
		USD: "$",
		ILS: "₪",
		JOD: "د.أ",
		EUR: "€",
		AED:
			document.querySelector('meta[name="pos-currency-symbol"]')?.getAttribute("content") || "د.إ",
		SAR: "ر.س",
		EGP: "ج.م",
		GBP: "£",
		KWD: "د.ك",
		QAR: "ر.ق",
		OMR: "ر.ع",
		BHD: "د.ب",
	};
	const currencySymbolFor = (code) => CURRENCY_SYMBOLS[code] || code;
	const loadOrderTypes = async () => {
		const sel = qs("#orderType");
		if (!sel) return;
		try {
			const r = await fetch("/pos/api/order-types", {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			});
			const data = await r.json();
			if (!data.success) return;
			sel.innerHTML = "";
			(data.order_types || []).forEach((ot) => {
				const o = document.createElement("option");
				o.value = ot.code;
				o.textContent = ot.display_name;
				sel.appendChild(o);
			});
			if (data.default_code) sel.value = data.default_code;
		} catch (_) {}
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
		// Quick local estimate (for responsive UI)
		const quickTax = pricesIncludeVatMeta ? 0 : subtotal * (taxRate / 100);
		const quickTotal = Math.max(0, subtotal + quickTax + shipping - discountAmount);
		qs("#kpiSubtotal").textContent = fmt(subtotal);
		qs("#kpiDiscount").textContent = fmt(discount + discountAmount);
		qs("#kpiTotal").textContent = fmt(quickTotal);
		qs("#kpiCurrency").textContent = currencySymbolFor(selectedCurrency());
		// Backend API for exact calculation (handles prices_include_vat correctly)
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
				const data = await r.json();
				if (data.success) {
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
		return quickTotals;
	};
	// Upsell prompts: live evaluation while composing the cart, plus a recap
	// inside the done modal after checkout (server returns upsell_prompts).
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
		upsellTimer = setTimeout(() => void evaluateUpsell(), 400);
	};

	const renderCart = async () => {
		const body = qs("#cartBody");
		body.innerHTML = "";
		const cnt = qs("#cartCount");
		if (cnt) cnt.textContent = String(state.cart.length);
		if (!state.cart.length) {
			body.innerHTML =
				'<tr id="cartEmptyRow"><td colspan="6" class="text-center text-muted py-4">السلة فارغة</td></tr>';
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

	qs("#cartBody").addEventListener("click", (e) => {
		const btn = e.target.closest("button[data-act]");
		if (!btn) return;
		const idx = Number(btn.getAttribute("data-i"));
		if (!Number.isFinite(idx) || !state.cart[idx]) return;
		const act = btn.getAttribute("data-act");
		if (act === "inc") state.cart[idx].qty = Number(state.cart[idx].qty) + 1;
		if (act === "dec") state.cart[idx].qty = Math.max(0.001, Number(state.cart[idx].qty) - 1);
		void renderCart();
	});
	const addToCart = async (p, qty = 1) => {
		state.idemKey = newCartKey();
		const existing = state.cart.find((x) => x.id === p.id);
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
			});
		}
		await renderCart();
	};
	const warehouseParam = () => {
		const w = qs("#warehouseId").value;
		return w ? `&warehouse_id=${encodeURIComponent(w)}` : "";
	};
	const fetchJson = async (url) => {
		const r = await fetch(url, {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		});
		if (r.status === 404) {
			const j = await r.json().catch(() => ({}));
			return { ok: false, error: j.error || "غير موجود" };
		}
		if (!r.ok) {
			const j = await r.json().catch(() => ({}));
			return { ok: false, error: j.error || `HTTP ${r.status}` };
		}
		const data = await r.json();
		return { ok: true, data };
	};
	let customerTimer = null;
	qs("#customerSearch").addEventListener("input", function () {
		const q = this.value.trim();
		clearTimeout(customerTimer);
		customerTimer = setTimeout(async () => {
			if (!q) {
				qs("#customerResults").classList.add("d-none");
				return;
			}
			const res = await fetchJson(`/pos/api/customers?q=${encodeURIComponent(q)}`);
			if (!res.ok) return;
			const box = qs("#customerResults");
			box.innerHTML = "";
			res.data.forEach((c) => {
				const a = document.createElement("button");
				a.type = "button";
				a.className = "list-group-item list-group-item-action";
				a.textContent = c.text;
				a.addEventListener("click", () => {
					state.customer = c;
					qs("#customerSearch").value = c.text;
					box.classList.add("d-none");
					customerHint();
				});
				box.appendChild(a);
			});
			box.classList.toggle("d-none", res.data.length === 0);
		}, 180);
	});
	qs("#clearCustomer").addEventListener("click", () => {
		state.customer = null;
		qs("#customerSearch").value = "";
		qs("#customerResults").classList.add("d-none");
		customerHint();
	});
	qs("#walkinCustomer").addEventListener("click", async () => {
		const res = await fetchJson("/pos/api/walkin-customer");
		if (!res.ok) return showAlert(res.error || "تعذر تحميل عميل نقدي");
		const c = res.data;
		state.customer = c;
		qs("#customerSearch").value = c.text || c.name;
		customerHint();
		qs("#productSearch").focus();
	});
	let productTimer = null;
	let productBusy = false;
	const renderProductResults = (res) => {
		state.lastProductResults = res || [];
		const box = qs("#productResults");
		box.innerHTML = "";
		(res || []).forEach((p) => {
			const a = document.createElement("button");
			a.type = "button";
			const stockBadge = p.is_out_of_stock
				? '<span class="badge badge-warning badge-pill ml-1">نفد</span>'
				: `<span class="badge badge-secondary badge-pill ml-1">${fmt(p.stock)}</span>`;
			a.className =
				"list-group-item list-group-item-action d-flex justify-content-between align-items-center";
			a.innerHTML = `<span>${esc(p.text)}${p.is_inactive ? ' <small class="text-danger">(غير نشط)</small>' : ""}</span><span>${stockBadge} <span class="badge badge-primary badge-pill">${fmt(priceForCurrency(p.price))} ${currencySymbolFor(selectedCurrency())}</span></span>`;
			a.addEventListener("click", async () => {
				if (p.is_inactive) {
					showAlert("المنتج غير نشط.", "warning");
					return;
				}
				await addToCart(p);
				qs("#productSearch").value = "";
				box.classList.add("d-none");
				qs("#productSearch").focus();
			});
			box.appendChild(a);
		});
		box.classList.toggle("d-none", !res || res.length === 0);
	};
	const addFirstOrLookup = async (q) => {
		if (!q) return;
		const first = (state.lastProductResults || [])[0];
		if (first && (first.barcode === q || first.sku === q)) {
			await addToCart(first);
			qs("#productSearch").value = "";
			qs("#productResults").classList.add("d-none");
			return;
		}
		const res = await fetchJson(
			`/pos/api/product?code=${encodeURIComponent(q)}${warehouseParam()}`,
		);
		if (!res.ok) {
			if ((state.lastProductResults || []).length) {
				await addToCart(state.lastProductResults[0]);
				qs("#productSearch").value = "";
				qs("#productResults").classList.add("d-none");
			}
			return;
		}
		const p = res.data;
		if (p?.id) {
			if (p.is_inactive) {
				showAlert(p.warning || "المنتج غير نشط.", "warning");
				return;
			}
			if (p.warning) showAlert(p.warning, "warning");
			await addToCart(p);
			qs("#productSearch").value = "";
			qs("#productResults").classList.add("d-none");
		} else {
			showAlert(res.error || "لم يُعثر على المنتج");
		}
	};
	const runProductSearch = async (q) => {
		if (!q) {
			qs("#productResults").classList.add("d-none");
			state.lastProductResults = [];
			qs("#productLoading").classList.add("d-none");
			return;
		}
		if (productBusy) return;
		productBusy = true;
		qs("#productLoading").classList.remove("d-none");
		const res = await fetchJson(`/pos/api/products?q=${encodeURIComponent(q)}${warehouseParam()}`);
		if (res.ok) renderProductResults(res.data);
		else showAlert(res.error || "فشل البحث");
		productBusy = false;
		qs("#productLoading").classList.add("d-none");
	};
	qs("#productSearch").addEventListener("input", function () {
		const q = this.value.trim();
		clearTimeout(productTimer);
		productTimer = setTimeout(() => runProductSearch(q), 220);
	});
	qs("#productSearch").addEventListener("keydown", function (e) {
		if (e.key === "Enter") {
			e.preventDefault();
			void addFirstOrLookup(this.value.trim());
		}
	});
	qs("#warehouseId").addEventListener("change", () => {
		const q = qs("#productSearch").value.trim();
		if (q) void runProductSearch(q);
	});
	qs("#clearProductSearch").addEventListener("click", () => {
		qs("#productSearch").value = "";
		qs("#productResults").classList.add("d-none");
		state.lastProductResults = [];
	});
	qs("#cartBody").addEventListener("input", (e) => {
		const t = e.target;
		const idx = Number(t.getAttribute("data-i"));
		const k = t.getAttribute("data-k");
		if (!Number.isFinite(idx) || !state.cart[idx]) return;
		if (k === "qty") state.cart[idx].qty = Math.max(0.001, toNum(t.value));
		if (k === "price") {
			state.cart[idx].price = Math.max(0, toNum(t.value));
			state.cart[idx].basePrice =
				selectedCurrency() !== baseCurrency && currentRate() > 0
					? state.cart[idx].price * currentRate()
					: state.cart[idx].price;
		}
		if (k === "disc") state.cart[idx].discountPercent = Math.max(0, Math.min(100, toNum(t.value)));
		state.idemKey = newCartKey();
		void renderCart();
	});
	qs("#cartBody").addEventListener("click", (e) => {
		const btn = e.target.closest('button[data-k="del"]');
		if (!btn) return;
		const idx = Number(btn.getAttribute("data-i"));
		if (!Number.isFinite(idx)) return;
		state.cart.splice(idx, 1);
		state.idemKey = newCartKey();
		void renderCart();
	});
	qsa("#taxRate,#shippingCost,#discountAmount").forEach((el) => {
		el.addEventListener("input", recalc);
		el.addEventListener("change", recalc);
	});
	qs("#currency").addEventListener("change", loadRateForCurrency);
	qs("#exchangeRate").addEventListener("input", updateCartPrices);
	qs("#exchangeRate").addEventListener("change", updateCartPrices);
	// Supervisor override: exchange a PIN for a single-use override token and
	// retry guarded requests (discount override / no-sale drawer open).
	let pinResolver = null;
	const settlePin = (token) => {
		if (pinResolver) {
			pinResolver(token);
			pinResolver = null;
		}
	};
	const requestOverrideToken = (action) =>
		new Promise((resolve) => {
			const modalEl = qs("#posPinModal");
			if (!modalEl) {
				resolve(null);
				return;
			}
			pinResolver = resolve;
			modalEl.dataset.action = action;
			qs("#posPinInput").value = "";
			qs("#posPinError").classList.add("d-none");
			$("#posPinModal").modal("show");
			setTimeout(() => qs("#posPinInput").focus(), 300);
		});
	const confirmPin = async () => {
		const err = qs("#posPinError");
		const action = qs("#posPinModal").dataset.action || "";
		const pin = qs("#posPinInput").value.trim();
		try {
			const r = await fetch("/pos/api/authorize-override", {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-CSRFToken": csrf,
				},
				credentials: "same-origin",
				body: JSON.stringify({ pin, action }),
			});
			const j = await r.json().catch(() => ({}));
			if (r.ok && j.success && j.override_token) {
				$("#posPinModal").modal("hide");
				settlePin(j.override_token);
				return;
			}
			err.textContent = j.error || "تعذر التفويض";
			err.classList.remove("d-none");
		} catch (_) {
			err.textContent = "فشل الاتصال بالخادم";
			err.classList.remove("d-none");
		}
	};
	const postWithOverride = async (url, body, action) => {
		const send = async (token) => {
			const payload = token ? { ...body, override_token: token } : body;
			const r = await fetch(url, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-CSRFToken": csrf,
				},
				credentials: "same-origin",
				body: JSON.stringify(payload),
			});
			const j = await r.json().catch(() => ({}));
			return { r, j };
		};
		const first = await send(null);
		if (first.r.status !== 403) return first;
		const token = await requestOverrideToken(action);
		if (!token) return first;
		return send(token);
	};
	const needsOverride = (r, j) =>
		r.status === 403 && typeof j.error === "string" && j.error.includes("تفويض");

	qs("#posPinConfirm")?.addEventListener("click", () => void confirmPin());
	qs("#posPinInput")?.addEventListener("keydown", (e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			void confirmPin();
		}
	});
	$("#posPinModal").on("hidden.bs.modal", () => settlePin(null));
	qs("#drawerOpenBtn")?.addEventListener("click", async () => {
		try {
			const { r, j } = await postWithOverride(
				"/pos/api/drawer/open",
				{ reason: "فتح يدوي من الشاشة" },
				"no_sale_drawer",
			);
			if (r.ok && j.success) {
				showAlert("تم فتح الدرج", "success");
			} else {
				showAlert(j.error || "تعذر فتح الدرج", "warning");
			}
		} catch (_) {
			showAlert("فشل الاتصال بالخادم", "warning");
		}
	});

	// Split tender: multiple payment chunks in one checkout (server `payments`).
	const SPLIT_METHODS = [
		["cash", "نقدي"],
		["card", "بطاقة"],
		["bank_transfer", "تحويل بنكي"],
		["e_wallet", "محفظة إلكترونية"],
		["cheque", "شيك"],
	];
	const splitEnabled = () => qs("#splitTenderToggle")?.checked === true;
	const splitSumRefresh = () => {
		let sum = 0;
		qsa("#splitTenderRows .split-amount").forEach((inp) => {
			sum += toNum(inp.value) || 0;
		});
		const el = qs("#splitTenderSum");
		if (el) el.textContent = fmt(sum);
	};
	const addSplitRow = (amount, method) => {
		const rows = qs("#splitTenderRows");
		if (!rows) return;
		const row = document.createElement("div");
		row.className = "split-row d-flex align-items-center mb-1";
		const amountInp = document.createElement("input");
		amountInp.type = "number";
		amountInp.step = "0.01";
		amountInp.min = "0";
		amountInp.className = "form-control form-control-sm split-amount mr-1";
		amountInp.value = amount || "";
		const methodSel = document.createElement("select");
		methodSel.className = "form-control form-control-sm split-method mr-1";
		SPLIT_METHODS.forEach(([val, label]) => {
			const opt = document.createElement("option");
			opt.value = val;
			opt.textContent = label;
			methodSel.appendChild(opt);
		});
		methodSel.value = method || "cash";
		const removeBtn = document.createElement("button");
		removeBtn.type = "button";
		removeBtn.className = "btn btn-sm btn-outline-danger split-remove";
		removeBtn.textContent = "×";
		removeBtn.addEventListener("click", () => {
			row.remove();
			splitSumRefresh();
		});
		amountInp.addEventListener("input", splitSumRefresh);
		row.appendChild(amountInp);
		row.appendChild(methodSel);
		row.appendChild(removeBtn);
		rows.appendChild(row);
		splitSumRefresh();
	};
	const readSplitPayments = () => {
		const rows = qsa("#splitTenderRows .split-row");
		if (!rows.length) {
			showAlert("أضف دفعة واحدة على الأقل أو أوقف الدفع المتعدد", "warning");
			return null;
		}
		const cur = qs("#currency").value;
		const rate = toNum(qs("#exchangeRate").value) || 1;
		const chunks = [];
		for (const row of rows) {
			const amount = toNum(row.querySelector(".split-amount")?.value) || 0;
			const method = row.querySelector(".split-method")?.value || "";
			if (amount <= 0 || !method) {
				showAlert("كل دفعة تحتاج مبلغاً أكبر من صفر وطريقة دفع", "warning");
				return null;
			}
			chunks.push({ amount, payment_method: method, currency: cur, exchange_rate: rate });
		}
		return chunks;
	};
	qs("#splitTenderToggle")?.addEventListener("change", (e) => {
		const box = qs("#splitTenderBox");
		box?.classList.toggle("d-none", !e.target.checked);
		if (e.target.checked && !qsa("#splitTenderRows .split-row").length) {
			addSplitRow(qs("#kpiTotal")?.textContent || "", qs("#paymentMethod")?.value || "cash");
		}
	});
	qs("#splitTenderAdd")?.addEventListener("click", () => addSplitRow("", "cash"));

	let checkoutBusy = false;
	const checkout = async (autoPrint) => {
		if (checkoutBusy) return;
		if (!state.customer) {
			showAlert("يرجى اختيار العميل أو «نقدي».", "warning");
			return;
		}
		if (!state.cart.length) {
			showAlert("السلة فارغة.", "warning");
			return;
		}
		const _totals = await recalc();
		const payload = {
			idempotency_key: state.idemKey,
			customer_id: state.customer.id,
			quick_customer: !!state.customer.is_walkin,
			warehouse_id: qs("#warehouseId").value || null,
			currency: qs("#currency").value,
			exchange_rate: toNum(qs("#exchangeRate").value) || 1,
			tax_rate: toNum(qs("#taxRate").value) || 0,
			shipping_cost: toNum(qs("#shippingCost").value) || 0,
			discount_amount: toNum(qs("#discountAmount").value) || 0,
			payment_method: qs("#paymentMethod").value || "",
			order_type: qs("#orderType") ? qs("#orderType").value : "takeaway",
			paid_amount: toNum(qs("#paidAmount").value) || 0,
			payment_currency: qs("#currency").value,
			payment_exchange_rate: toNum(qs("#exchangeRate").value) || 1,
			reference_number: qs("#referenceNumber").value || "",
			notes: qs("#orderNote") ? qs("#orderNote").value || "" : "",
			lines: state.cart.map((it) => ({
				product_id: it.id,
				quantity: it.qty,
				unit_price: it.price,
				discount_percent: it.discountPercent,
			})),
		};
		if (splitEnabled()) {
			const chunks = readSplitPayments();
			if (!chunks) return;
			payload.payments = chunks;
		}
		checkoutBusy = true;
		qs("#checkoutBtn").disabled = true;
		qs("#checkoutBtn").classList.add("loading");
		qs("#checkoutPrintBtn").disabled = true;
		qs("#checkoutPrintBtn").classList.add("loading");
		try {
			const sendCheckout = (token) => {
				const body = token ? { ...payload, override_token: token } : payload;
				return fetch("/pos/api/checkout", {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Accept: "application/json",
						"X-CSRFToken": csrf,
						"Idempotency-Key": state.idemKey,
					},
					credentials: "same-origin",
					body: JSON.stringify(body),
				});
			};
			let r = await sendCheckout(null);
			let j = await r.json().catch(() => ({}));
			if (needsOverride(r, j)) {
				const token = await requestOverrideToken("discount_override");
				if (token) {
					r = await sendCheckout(token);
					j = await r.json().catch(() => ({}));
				}
			}
			if (!r.ok || !j.success) {
				showError(j.error || `HTTP ${r.status}`);
				return;
			}
			qs("#doneSaleNumber").textContent = j.sale_number;
			renderUpsellMessages(qs("#doneUpsellList"), j.upsell_prompts);
			qs("#doneViewBtn").href = j.view_url;
			qs("#donePrintBtn").href = j.print_url;
			$("#posDoneModal").modal("show");
			if (autoPrint) {
				window.open(j.print_url, "_blank", "noopener");
			}
			state.cart = [];
			state.idemKey = newCartKey();
			await renderCart();
			qs("#paidAmount").value = 0;
			const splitToggle = qs("#splitTenderToggle");
			if (splitToggle) splitToggle.checked = false;
			qs("#splitTenderBox")?.classList.add("d-none");
			const splitRows = qs("#splitTenderRows");
			if (splitRows) splitRows.innerHTML = "";
			qs("#paymentMethod").value = "";
			qs("#referenceNumber").value = "";
			if (qs("#orderNote")) qs("#orderNote").value = "";
			if (typeof syncPay === "function") syncPay();
			if (selectedTable && j.sale_id) {
				try {
					await fetch(`/pos/api/tables/${selectedTable.id}/assign`, {
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							"X-CSRFToken": csrf,
						},
						credentials: "same-origin",
						body: JSON.stringify({ sale_id: j.sale_id }),
					});
				} catch (_) {}
				selectedTable = null;
				const tb = qs("#posTablesBtn");
				if (tb) tb.title = "إدارة الطاولات";
				const ts = qs("#posTableSelected");
				if (ts) ts.textContent = "";
			}
		} catch (err) {
			showAlert(err.message || "فشل العملية");
		} finally {
			checkoutBusy = false;
			qs("#checkoutBtn").disabled = false;
			qs("#checkoutBtn").classList.remove("loading");
			qs("#checkoutPrintBtn").disabled = false;
			qs("#checkoutPrintBtn").classList.remove("loading");
		}
	};
	qs("#checkoutBtn").addEventListener("click", () => checkout(false));
	qs("#checkoutPrintBtn").addEventListener("click", () => checkout(true));
	document.addEventListener("keydown", (e) => {
		if (e.target.matches("input, textarea, select") && e.key !== "Escape" && !e.altKey) {
			if (e.key === "F2" || e.key === "F4" || e.key === "F8") {
			} else return;
		}
		if (e.key === "F2") {
			e.preventDefault();
			qs("#productSearch").focus();
		} else if (e.key === "F4") {
			e.preventDefault();
			qs("#customerSearch").focus();
		} else if (e.key === "F8") {
			e.preventDefault();
			void checkout(true);
		} else if (e.key === "Escape") {
			qs("#productSearch").value = "";
			qs("#productResults").classList.add("d-none");
			state.lastProductResults = [];
		}
	});
	customerHint();
	void renderCart();
	qs("#productSearch").focus();
	const handleScannedCode = async (code) => {
		if (!code?.trim()) return;
		const res = await fetchJson(
			`/pos/api/product?code=${encodeURIComponent(code.trim())}${warehouseParam()}`,
		);
		if (!res.ok) return;
		const p = res.data;
		if (p?.id) {
			if (p.is_inactive) {
				showAlert(p.warning || "المنتج غير نشط.", "warning");
				return;
			}
			const liveKg = Number(state.scaleWeightKg) || 0;
			const qty = p.is_weight_product && liveKg > 0 ? liveKg : p.scale_weight_kg || 1;
			await addToCart(p, qty);
			qs("#productSearch").value = "";
			qs("#productResults").classList.add("d-none");
			showAlert(`تمت إضافة ${p.name}`, "success");
		}
	};
	state.barcodeScanner = new BarcodeScanner({ onScan: handleScannedCode });
	state.barcodeScanner.start();
	if (window.setupCameraScanUI) {
		setupCameraScanUI({
			button: qs("#cameraScanBtn"),
			onScan: (code) => void handleScannedCode(code),
			onError: (msg) => showAlert(msg, "warning"),
		});
	}
	if (window.PosScaleSerial && window.setupPosScaleUI) {
		const scaleBtn = qs("#scaleConnectBtn");
		state.posScale = new PosScaleSerial({
			onStableWeight: (kg) => {
				state.scaleWeightKg = kg;
				if (scaleBtn) scaleBtn.dataset.liveWeight = kg.toFixed(3);
			},
			onError: (msg) => showAlert(msg, "warning"),
		});
		setupPosScaleUI({
			button: scaleBtn,
			scale: state.posScale,
			connectedTitle: scaleBtn?.dataset.scaleOnTitle,
		});
	}

	/* ---------- Calculator (edits #paidAmount) ---------- */
	const paidEl = qs("#paidAmount");
	const calcGrid = qs("#posCalc");
	const curPaid = () => (paidEl.value === "" || paidEl.value == null ? "0" : String(paidEl.value));
	if (calcGrid && paidEl) {
		calcGrid.addEventListener("click", (e) => {
			const b = e.target.closest("button[data-act]");
			if (!b) return;
			const act = b.getAttribute("data-act");
			let cur = curPaid();
			if (act === "digit") {
				cur = cur === "0" ? "" : cur;
				cur += b.getAttribute("data-val");
			} else if (act === "dot") {
				if (!cur.includes(".")) cur += ".";
			} else if (act === "back") {
				cur = cur.length > 1 ? cur.slice(0, -1) : "0";
			} else if (act === "clear") {
				cur = "0";
			} else if (act === "add") {
				cur = (toNum(cur) + toNum(b.getAttribute("data-val"))).toFixed(2).replace(/\.00$/, "");
			}
			paidEl.value = cur;
			if (typeof recalc === "function") recalc();
		});
		paidEl.addEventListener("input", () => {
			/* keep in sync if typed manually */
		});
	}

	/* ---------- Payment method chips ---------- */
	const paySel = qs("#paymentMethod");
	const refField = qs("#refField");
	const syncPay = () => {
		const v = paySel ? paySel.value : "";
		qsa("#posPayMethod .pm").forEach((pm) => {
			pm.classList.toggle("active", pm.getAttribute("data-method") === v);
		});
		if (refField) refField.classList.toggle("show", !!v);
	};
	qsa("#posPayMethod .pm").forEach((pm) => {
		pm.addEventListener("click", () => {
			if (paySel) paySel.value = pm.getAttribute("data-method");
			syncPay();
		});
	});
	if (paySel) paySel.addEventListener("change", syncPay);
	syncPay();

	/* ---------- Push-to-terminal card payment ---------- */
	if (window.setupTerminalButton) {
		void setupTerminalButton({
			button: qs("#pushTerminalBtn"),
			getAmount: () => state.lastTotals?.total || 0,
			getCurrency: () => selectedCurrency(),
			onApproved: (result) => {
				if (paidEl && state.lastTotals) paidEl.value = String(state.lastTotals.total);
				showAlert(`تمت الموافقة على الدفع بالبطاقة (${result.intentId})`, "success");
			},
			onError: (msg) => showAlert(msg, "warning"),
		});
	}

	/* ---------- Categories + product grid ---------- */
	const loadCategories = async () => {
		const box = qs("#posCategories");
		if (!box) return;
		const res = await fetchJson("/pos/api/categories");
		if (!res.ok) return;
		const cats = res.data;
		if (!cats) return;
		let html = '<div class="pos-cat active" data-cat="">الكل</div>';
		cats.forEach((c) => {
			const name = c.name_ar || c.name;
			html += `<div class="pos-cat" data-cat="${c.id}">${esc(name)}</div>`;
		});
		box.innerHTML = html;
		box.querySelectorAll(".pos-cat").forEach((el) => {
			el.addEventListener("click", () => {
				box.querySelectorAll(".pos-cat").forEach((x) => void x.classList.remove("active"));
				el.classList.add("active");
				void loadProducts(el.getAttribute("data-cat"));
			});
		});
	};
	const loadProducts = async (categoryId) => {
		const grid = qs("#posProductGrid");
		if (!grid) return;
		grid.innerHTML =
			'<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i> جاري التحميل...</div>';
		try {
			const url =
				"/pos/api/products?per_page=60" +
				(categoryId ? `&category_id=${encodeURIComponent(categoryId)}` : "") +
				warehouseParam();
			const res = await fetchJson(url);
			if (!res.ok || !res.data?.length) {
				grid.innerHTML = '<div class="pos-cart-empty">لا توجد منتجات</div>';
				return;
			}
			grid.innerHTML = "";
			res.data.forEach((p) => {
				const card = document.createElement("div");
				card.className = `pos-card${p.is_out_of_stock ? " out" : ""}`;
				const badge = p.is_inactive
					? '<span class="badge danger">غير نشط</span>'
					: p.is_out_of_stock
						? '<span class="badge danger">نفد</span>'
						: p.stock <= 5
							? `<span class="badge warn">${fmt(p.stock)}</span>`
							: "";
				card.innerHTML = `
                    <div class="icon">📦</div>
                    <div class="name">${esc(p.name)}</div>
                    <div class="meta">
                        <span class="price">${fmt(priceForCurrency(p.price))} ${currencySymbolFor(selectedCurrency())}</span>
                        ${badge}
                    </div>
                `;
				card.addEventListener("click", async () => {
					if (p.is_inactive) {
						showAlert("المنتج غير نشط.", "warning");
						return;
					}
					await addToCart(p);
					qs("#productSearch").focus();
				});
				grid.appendChild(card);
			});
		} catch (_err) {
			grid.innerHTML = '<div class="pos-cart-empty">تعذر تحميل المنتجات</div>';
		}
	};
	void loadCategories();
	void loadProducts("");

	/* ---------- Ctrl+K focuses product search ---------- */
	document.addEventListener("keydown", (e) => {
		if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
			e.preventDefault();
			qs("#productSearch").focus();
		}
	});

	/* ---------- Runtime profile: restaurant tables + hold (from window.POS_CONFIG) ---------- */
	const POS_CONFIG = window.POS_CONFIG || {
		enable_tables: false,
		enable_hold: true,
	};
	const tablesBtn = qs("#posTablesBtn");
	const holdBtn = qs("#posHoldBtn");
	let selectedTable = null;
	if (POS_CONFIG.enable_tables && tablesBtn) tablesBtn.classList.remove("d-none");
	if (POS_CONFIG.enable_hold && holdBtn) holdBtn.classList.remove("d-none");

	const loadFloors = async () => {
		const box = qs("#posFloors");
		const _grid = qs("#posTablesGrid");
		const res = await fetchJson("/pos/api/floors");
		if (!res.ok) return;
		const floors = res.data;
		if (!floors?.length) {
			box.innerHTML = '<div class="pos-cart-empty">لا توجد أرضيات</div>';
		} else {
			box.innerHTML = floors
				.map((f) => `<div class="pos-cat" data-floor="${f.id}">${esc(f.name_ar || f.name)}</div>`)
				.join("");
			box.querySelectorAll(".pos-cat").forEach((el) => {
				el.addEventListener("click", () => {
					box.querySelectorAll(".pos-cat").forEach((x) => void x.classList.remove("active"));
					el.classList.add("active");
					void loadTables(el.getAttribute("data-floor"));
				});
			});
		}
	};
	const loadTables = async (floorId) => {
		const grid = qs("#posTablesGrid");
		grid.innerHTML = '<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i></div>';
		const res = await fetchJson(`/pos/api/floors/${floorId}/tables`);
		if (!res.ok) {
			grid.innerHTML = '<div class="pos-cart-empty">تعذر التحميل</div>';
			return;
		}
		const tables = res.data;
		if (!tables) {
			grid.innerHTML = '<div class="pos-cart-empty">تعذر التحميل</div>';
			return;
		}
		grid.innerHTML = "";
		tables.forEach((t) => {
			const occupied = t.status && t.status !== "free";
			const card = document.createElement("div");
			card.className = `pos-card${occupied ? " out" : ""}`;
			card.innerHTML = `<div class="icon">🪑</div><div class="name">${esc(t.label)}</div><div class="meta"><span class="price">${esc(t.status || "free")}</span></div>`;
			card.addEventListener("click", () => {
				selectedTable = { id: t.id, label: t.label };
				const sel = qs("#posTableSelected");
				if (sel) sel.textContent = `الطاولة المحددة: ${t.label}`;
				if (tablesBtn) tablesBtn.title = `الطاولة: ${t.label}`;
				if (window.jQuery) $("#posTablesModal").modal("hide");
			});
			grid.appendChild(card);
		});
	};
	if (tablesBtn) {
		tablesBtn.addEventListener("click", loadFloors);
		const clearT = qs("#posTableClear");
		if (clearT)
			clearT.addEventListener("click", () => {
				selectedTable = null;
				const sel = qs("#posTableSelected");
				if (sel) sel.textContent = "";
				if (tablesBtn) tablesBtn.title = "إدارة الطاولات";
			});
	}

	const HOLD_KEY = "pos_held_carts";
	const heldCount = () => {
		try {
			return JSON.parse(localStorage.getItem(HOLD_KEY) || "[]").length;
		} catch (_) {
			return 0;
		}
	};
	if (holdBtn) {
		holdBtn.addEventListener("click", async () => {
			const list = JSON.parse(localStorage.getItem(HOLD_KEY) || "[]");
			if (!state.cart.length) {
				if (!list.length) {
					showAlert("لا توجد فواتير معلّقة", "warning");
					return;
				}
				const last = list.pop();
				localStorage.setItem(HOLD_KEY, JSON.stringify(list));
				state.cart = last.cart || [];
				state.idemKey = newCartKey();
				state.customer = last.customer || null;
				selectedTable = last.table || null;
				if (qs("#orderNote")) qs("#orderNote").value = last.note || "";
				await renderCart();
				customerHint();
				showAlert("تم استئناف الفاتورة المعلّقة", "success");
				return;
			}
			list.push({
				cart: state.cart,
				customer: state.customer,
				table: selectedTable,
				note: qs("#orderNote") ? qs("#orderNote").value || "" : "",
				ts: Date.now(),
			});
			localStorage.setItem(HOLD_KEY, JSON.stringify(list));
			state.cart = [];
			state.idemKey = newCartKey();
			await renderCart();
			if (qs("#orderNote")) qs("#orderNote").value = "";
			showAlert(`تم تعليق الفاتورة (${heldCount()} معلّقة)`, "success");
		});
	}

	async function loadSession() {
		try {
			const r = await fetch("/pos/api/session/current", {
				credentials: "same-origin",
			});
			const j = await r.json();
			const bar = qs("#posSessionBar");
			const required = qs("#posSessionRequired");
			if (j.success && j.session) {
				const s = j.session;
				if (window.cfdBroadcast) cfdBroadcast.setSession(s.id);
				bar.classList.remove("d-none");
				required.classList.add("d-none");
				qs("#sessionNumber").textContent = s.number;
				qs("#sessionBalance").textContent = fmt(s.opening_balance);
				qs("#sessionTotal").textContent = fmt(s.total_sales);
				qs("#sessionTime").textContent = `مفتوحة منذ ${s.duration_minutes} دقيقة`;
				qs("#closeOpening").textContent = fmt(s.opening_balance);
			} else {
				if (window.cfdBroadcast) cfdBroadcast.setSession(null);
				bar.classList.add("d-none");
				required.classList.remove("d-none");
			}
		} catch (_) {}
	}

	qs("#openSessionBtn").addEventListener("click", () => {
		qs("#openSessionBalance").value = "0";
		qs("#openSessionNotes").value = "";
		$("#openSessionModal").modal("show");
	});

	qs("#openSessionConfirm").addEventListener("click", async () => {
		const balance = toNum(qs("#openSessionBalance").value);
		const notes = qs("#openSessionNotes").value.trim();
		hideModalAlert("openSession");
		qs("#openSessionConfirm").disabled = true;
		try {
			const r = await fetch("/pos/api/session/open", {
				method: "POST",
				headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
				credentials: "same-origin",
				body: JSON.stringify({
					opening_balance: balance,
					notes: notes || undefined,
				}),
			});
			const j = await r.json();
			if (!r.ok || !j.success) {
				showModalAlert("openSession", j.error || "فشل فتح الجلسة", "danger");
				return;
			}
			$("#openSessionModal").modal("hide");
			await loadSession();
			showAlert(`تم فتح الجلسة: ${j.session.number}`, "success");
		} catch (err) {
			showModalAlert("openSession", err.message, "danger");
		} finally {
			qs("#openSessionConfirm").disabled = false;
		}
	});

	qs("#closeSessionBtn").addEventListener("click", async () => {
		hideModalAlert("closeSession");
		try {
			const r = await fetch("/pos/api/session/report", {
				credentials: "same-origin",
			});
			const j = await r.json();
			if (j.success && j.session) {
				qs("#closeOpening").textContent = fmt(j.session.opening_balance);
				const canViewSensitive =
					j.session.total_cash_sales !== undefined && j.session.expected_balance !== undefined;
				qs("#closeExpectedBlock").classList.toggle("d-none", !canViewSensitive);
				if (canViewSensitive) {
					qs("#closeCashSales").textContent = fmt(j.session.total_cash_sales);
					qs("#closeExpected").textContent = fmt(j.session.expected_balance);
				}
			}
		} catch (err) {
			showModalAlert(
				"closeSession",
				`تعذر تحميل بيانات الجلسة: ${err.message || "خطأ غير معروف"}`,
				"warning",
			);
		}
		qs("#closeSessionBalance").value = "";
		qs("#closeSessionNotes").value = "";
		$("#closeSessionModal").modal("show");
	});

	qs("#closeSessionConfirm").addEventListener("click", async () => {
		const balance = toNum(qs("#closeSessionBalance").value);
		if (Number.isNaN(Number(qs("#closeSessionBalance").value))) {
			showModalAlert("closeSession", "يرجى إدخال رصيد الإغلاق.", "warning");
			return;
		}
		const notes = qs("#closeSessionNotes").value.trim();
		hideModalAlert("closeSession");
		qs("#closeSessionConfirm").disabled = true;
		try {
			const r = await fetch("/pos/api/session/close", {
				method: "POST",
				headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
				credentials: "same-origin",
				body: JSON.stringify({
					closing_balance: balance,
					notes: notes || undefined,
				}),
			});
			const j = await r.json();
			if (!r.ok || !j.success) {
				showModalAlert("closeSession", j.error || "فشل إغلاق الجلسة", "danger");
				return;
			}
			$("#closeSessionModal").modal("hide");
			await loadSession();
			const diff = j.session.difference;
			if (Math.abs(diff) > 0.01) {
				showAlert(`تم إغلاق الجلسة. فرق الرصيد: ${fmt(diff)}`, diff < 0 ? "danger" : "warning");
			} else {
				showAlert("تم إغلاق الجلسة بنجاح. الرصيد مطابق.", "success");
			}
		} catch (err) {
			showModalAlert("closeSession", err.message, "danger");
		} finally {
			qs("#closeSessionConfirm").disabled = false;
		}
	});

	$("#posDoneModal").on("hidden.bs.modal", () => {
		qs("#productSearch").focus();
	});
	loadOrderTypes();
	void loadSession();
})();
