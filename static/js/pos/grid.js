(() => {
	const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
	const state = {
		customer: null,
		cart: [],
		lastProductResults: [],
		barcodeScanner: null,
		selectedCategory: "",
		numpadBuffer: "",
		numpadMode: null,
		selectedLine: null,
	};
	// One idempotency key per cart lifecycle — bumped on every cart mutation
	// and after each successful checkout (see index.js for the same contract).
	const newCartKey = () =>
		window.crypto && crypto.randomUUID
			? crypto.randomUUID()
			: `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;
	state.idemKey = newCartKey();
	// Module-scope busy/timer guards — shared by the session handlers, the
	// checkout double-click guard, and the product-search debounce.
	let _sessionBusy = false;
	let checkoutBusy = false;
	let productSearchTimer = null;
	// Session-expiry safety net: a 401 from any POS endpoint means the
	// session ended — bounce to login instead of every later call silently
	// failing (403 permission errors keep the existing override flow).
	const rawFetch = window.fetch.bind(window);
	let _sessionRedirected = false;
	const fetch = (url, options) =>
		rawFetch(url, options).then((r) => {
			if (r.status === 401 && !_sessionRedirected) {
				_sessionRedirected = true;
				window.location.href = "/auth/login";
			}
			return r;
		});
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
	const pricesIncludeVatMeta =
		document.querySelector('meta[name="pos-prices-include-vat"]')?.getAttribute("content") ===
		"true";
	const CURRENCY_SYMBOLS = {
		USD: "$",
		ILS: "₪",
		JOD: "د.أ",
		EUR: "€",
		AED: "د.إ",
		SAR: "ر.س",
		EGP: "ج.م",
		GBP: "£",
		KWD: "د.ك",
		QAR: "ر.ق",
		OMR: "ر.ع",
		BHD: "د.ب",
	};
	// The tenant base currency row shows the tenant-configured symbol, not a hardcoded one.
	const tenantPosSymbol = document
		.querySelector('meta[name="pos-currency-symbol"]')
		?.getAttribute("content");
	if (baseCurrency && tenantPosSymbol) CURRENCY_SYMBOLS[baseCurrency] = tenantPosSymbol;
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
			toggleTableField();
		} catch (_) {}
	};
	// Restaurant mode: show the table selector for dine-in style order types
	const toggleTableField = () => {
		const tableField = qs("#tableField");
		const sel = qs("#orderType");
		if (!tableField || !sel) return;
		const code = (sel.value || "").toLowerCase();
		const needsTable = code.includes("dine") || code.includes("table");
		tableField.classList.toggle("d-none", !needsTable);
		if (needsTable) loadTables();
	};
	const loadTables = async () => {
		const sel = qs("#tableSelect");
		if (!sel || sel.dataset.loaded) return;
		try {
			const r = await fetch("/pos/api/tables", {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			});
			const tables = await r.json();
			(tables || []).forEach((t) => {
				const o = document.createElement("option");
				o.value = t.id;
				o.textContent = t.floor_name ? `${t.label} — ${t.floor_name}` : t.label;
				sel.appendChild(o);
			});
			sel.dataset.loaded = "1";
		} catch (_) {}
	};
	const orderTypeSel = qs("#orderType");
	if (orderTypeSel) orderTypeSel.addEventListener("change", toggleTableField);
	const esc = (s) => {
		if (s == null) return "";
		return String(s)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	};
	const showAlert = (msg, level = "danger") => {
		let el = qs("#posAlert");
		if (!el) {
			el = document.createElement("div");
			el.id = "posAlert";
			el.className = "alert d-none";
			document.querySelector(".pos-cart-panel").prepend(el);
		}
		el.className = `alert alert-${level}`;
		el.textContent = msg;
		el.classList.remove("d-none");
		setTimeout(() => {
			el.classList.add("d-none");
		}, 5000);
	};
	const selectedCurrency = () => qs("#currency")?.value || baseCurrency;
	const currentRate = () => toNum(qs("#exchangeRate")?.value) || 1;
	const priceForCurrency = (basePrice) => {
		const rate = currentRate();
		if (selectedCurrency() !== baseCurrency && rate > 0) {
			return toNum(basePrice) / rate;
		}
		return toNum(basePrice);
	};
	const loadRateForCurrency = async () => {
		const cur = selectedCurrency();
		if (cur === baseCurrency) {
			if (qs("#exchangeRate")) qs("#exchangeRate").value = "1";
			await updateCartPrices();
			return;
		}
		try {
			const r = await fetch(
				`/api/currency-rate/${encodeURIComponent(cur)}/${encodeURIComponent(baseCurrency)}`,
			);
			const d = await r.json();
			if (d.success && d.rate && qs("#exchangeRate")) {
				qs("#exchangeRate").value = Number(d.rate).toFixed(6);
			}
		} catch (_) {}
		await updateCartPrices();
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

	const recalc = async () => {
		const taxRate = Math.max(0, Math.min(100, toNum(qs("#taxRate")?.value)));
		const shipping = Math.max(0, toNum(qs("#shippingCost")?.value));
		const discountAmount = Math.max(0, toNum(qs("#discountAmount")?.value));
		let subtotal = 0,
			lineDiscount = 0;
		state.cart.forEach((it) => {
			const lineBase = it.qty * it.price;
			const lineDisc = lineBase * (it.discountPercent / 100);
			subtotal += lineBase - lineDisc;
			lineDiscount += lineDisc;
		});
		const quickTax = pricesIncludeVatMeta ? 0 : subtotal * (taxRate / 100);
		const quickTotal = Math.max(0, subtotal + quickTax + shipping - discountAmount);
		qs("#kpiSubtotal").textContent = fmt(subtotal);
		qs("#kpiTax").textContent = fmt(quickTax);
		qs("#kpiDiscount").textContent = fmt(lineDiscount + discountAmount);
		qs("#kpiShipping").textContent = fmt(shipping);
		qs("#kpiTotal").textContent = fmt(quickTotal);
		qs("#kpiCurrency").textContent = currencySymbolFor(selectedCurrency());
		const taxRow = qs("#taxRow");
		if (taxRow) taxRow.style.display = taxRate > 0 ? "" : "none";
		if (state.cart.length > 0) {
			qs("#cartEmpty")?.classList.add("d-none");
			qs("#cartItems")?.classList.remove("d-none");
		} else {
			qs("#cartEmpty")?.classList.remove("d-none");
			qs("#cartItems")?.classList.add("d-none");
		}
		if (state.cart.length > 0) {
			try {
				const r = await fetch("/sales/api/calculate-totals", {
					method: "POST",
					headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
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
					qs("#kpiTax").textContent = fmt(data.tax_amount);
					qs("#kpiDiscount").textContent = fmt(data.discount);
					qs("#kpiTotal").textContent = fmt(data.total);
					qs("#kpiCurrency").textContent = currencySymbolFor(selectedCurrency());
					const exactTotals = {
						subtotal: data.subtotal,
						tax: data.tax_amount,
						shipping,
						discountAmount,
						lineDiscount,
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
			lineDiscount,
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
						product_id: it.productId,
						quantity: it.qty,
						unit_price: it.price,
						discount_percent: it.discountPercent || 0,
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
		const container = qs("#cartItems");
		container.innerHTML = "";
		state.cart.forEach((it, idx) => {
			const div = document.createElement("div");
			div.className = `pos-cart-item${state.selectedLine === idx ? " selected" : ""}`;
			div.dataset.idx = String(idx);
			const lineTotal = it.qty * it.price * (1 - (it.discountPercent || 0) / 100);
			div.innerHTML = `<div class="item-info"><div class="item-name">${esc(it.name)}</div><div class="item-price">${fmt(it.price)} x ${it.qty}${it.discountPercent ? ` (${it.discountPercent}% خصم)` : ""}</div></div><div class="item-qty"><button class="qty-minus" data-idx="${idx}">-</button><span>${it.qty}</span><button class="qty-plus" data-idx="${idx}">+</button></div><div class="item-total">${fmt(lineTotal)}</div><div class="item-remove" data-idx="${idx}"><i class="fas fa-times"></i></div>`;
			container.appendChild(div);
		});
		qsa(".qty-minus").forEach((b) => {
			b.addEventListener("click", async (e) => {
				const idx = Number(e.target.dataset.idx);
				state.idemKey = newCartKey();
				if (state.cart[idx]?.qty > 1) {
					state.cart[idx].qty--;
					await renderCart();
					await recalc();
				} else {
					state.cart.splice(idx, 1);
					await renderCart();
					await recalc();
				}
			});
		});
		qsa(".qty-plus").forEach((b) => {
			b.addEventListener("click", async (e) => {
				const idx = Number(e.target.dataset.idx);
				if (state.cart[idx]) {
					state.cart[idx].qty++;
					state.idemKey = newCartKey();
					await renderCart();
					await recalc();
				}
			});
		});
		qsa(".item-remove").forEach((b) => {
			b.addEventListener("click", async (e) => {
				const idx = Number(e.target.closest(".item-remove").dataset.idx);
				state.cart.splice(idx, 1);
				state.idemKey = newCartKey();
				await renderCart();
				await recalc();
			});
		});
		qsa(".pos-cart-item").forEach((item) => {
			item.addEventListener("click", (e) => {
				state.selectedLine = Number(e.currentTarget.dataset.idx);
				void renderCart();
			});
		});
		await recalc();
		scheduleUpsellEval();
	};

	const addToCart = async (product, qty = 1) => {
		const p = product.product || product;
		const existing = state.cart.find((c) => c.productId === p.id);
		const price = priceForCurrency(toNum(p.price));
		state.idemKey = newCartKey();
		if (existing) {
			existing.qty += qty;
			existing.price = price;
		} else {
			state.cart.push({
				productId: p.id,
				name: p.name_ar || p.name,
				price: price,
				basePrice: toNum(p.price),
				qty: qty,
				discountPercent: 0,
				sku: p.sku || "",
				barcode: p.barcode || "",
			});
		}
		await renderCart();
	};

	const renderProductGrid = (products) => {
		const grid = qs("#productGrid");
		grid.innerHTML = "";
		products.forEach((p) => {
			const card = document.createElement("div");
			card.className = `pos-product-card${p.is_out_of_stock ? " out-of-stock" : ""}`;
			card.dataset.id = p.id;
			const img = p.image_url
				? `<img src="${esc(p.image_url)}" class="prod-img" alt="">`
				: `<div class="prod-img d-flex align-items-center justify-content-center text-muted"><i class="fas fa-box fa-2x"></i></div>`;
			card.innerHTML = `${img}<div class="prod-name">${esc(p.name_ar || p.name)}</div><div class="prod-price">${fmt(p.price)}</div><div class="prod-stock ${p.stock <= 0 ? "out" : p.stock <= 5 ? "low" : ""}">${p.stock_label || ""}</div>`;
			if (!p.is_out_of_stock) {
				card.addEventListener("click", async () => {
					await addToCart(p, 1);
				});
			}
			grid.appendChild(card);
		});
	};

	const loadCategories = async () => {
		try {
			const r = await fetch("/pos/api/categories");
			const data = await r.json();
			const list = qs("#categoryList");
			list.innerHTML = "";
			data.forEach((cat) => {
				const div = document.createElement("div");
				div.className = "cat-item";
				div.dataset.catId = cat.id;
				div.innerHTML = `<i class="fas fa-tag mr-2"></i>${esc(cat.name_ar || cat.name)}`;
				div.addEventListener("click", () => {
					qsa(".cat-item").forEach((c) => void c.classList.remove("active"));
					div.classList.add("active");
					state.selectedCategory = cat.id;
					void loadProducts();
				});
				list.appendChild(div);
			});
		} catch (_) {}
	};

	const loadProducts = async (q = "") => {
		qs("#productLoading")?.classList.remove("d-none");
		try {
			const params = new URLSearchParams();
			if (q) params.append("q", q);
			if (state.selectedCategory) params.append("category_id", state.selectedCategory);
			const wid = qs("#warehouseId")?.value;
			if (wid) params.append("warehouse_id", wid);
			params.append("per_page", "40");
			const r = await fetch(`/pos/api/products?${params.toString()}`);
			const data = await r.json();
			state.lastProductResults = data;
			if (data.length > 0) {
				renderProductGrid(data);
				qs("#productResults")?.classList.add("d-none");
			} else {
				qs("#productGrid").innerHTML =
					'<div class="text-center text-muted py-5 w-100">لا توجد منتجات</div>';
			}
		} catch (_) {}
		qs("#productLoading")?.classList.add("d-none");
	};

	const handleNumpad = (key) => {
		if (key === "del") {
			state.numpadBuffer = state.numpadBuffer.slice(0, -1);
			return;
		}
		if (key === "Enter" && state.numpadMode && state.numpadBuffer && state.selectedLine !== null) {
			const val = toNum(state.numpadBuffer);
			const line = state.cart[state.selectedLine];
			if (!line) return;
			if (state.numpadMode === "qty" && val > 0) {
				line.qty = val;
			} else if (state.numpadMode === "disc" && val >= 0 && val <= 100) {
				line.discountPercent = val;
			} else if (state.numpadMode === "price" && val >= 0) {
				line.basePrice = val;
				line.price = priceForCurrency(val);
			}
			state.numpadBuffer = "";
			state.numpadMode = null;
			state.idemKey = newCartKey();
			void renderCart();
			void recalc();
			return;
		}
		if (key === "qty" || key === "disc" || key === "price") {
			if (state.selectedLine === null) {
				showAlert("اختر منتجاً من السلة أولاً", "warning");
				return;
			}
			state.numpadMode = key;
			state.numpadBuffer = "";
			const labels = { qty: "الكمية", disc: "نسبة الخصم", price: "السعر" };
			showAlert(`أدخل ${labels[key]} باستخدام لوحة الأرقام ثم اضغط Enter`, "info");
			return;
		}
		if (key.match(/^[0-9.]$/) && state.numpadMode) {
			state.numpadBuffer += key;
		}
	};

	const initSession = () => {
		fetch("/pos/api/session/current")
			.then((r) => r.json())
			.then((d) => {
				if (d.success && d.session) {
					if (window.cfdBroadcast) cfdBroadcast.setSession(d.session.id);
					qs("#posSessionBar").classList.remove("d-none");
					qs("#posSessionRequired").classList.add("d-none");
					qs("#sessionNumber").textContent = d.session.number;
					qs("#sessionBalance").textContent = fmt(d.session.opening_balance);
					qs("#sessionTotal").textContent = fmt(d.session.total_sales);
				} else {
					qs("#posSessionBar").classList.add("d-none");
					qs("#posSessionRequired").classList.remove("d-none");
				}
			})
			.catch(() => {});
	};

	const customerHint = () => {
		const el = qs("#customerSelectedHint");
		if (state.customer) {
			el.textContent = state.customer.text || state.customer.name;
			el.className = "text-success";
		} else {
			el.textContent = "لم يتم اختيار عميل";
			el.className = "text-muted";
		}
	};

	const searchCustomers = async (q) => {
		if (!q) {
			qs("#customerResults")?.classList.add("d-none");
			return;
		}
		try {
			const r = await fetch(`/pos/api/customers?q=${encodeURIComponent(q)}`);
			const data = await r.json();
			const list = qs("#customerResults");
			list.innerHTML = "";
			data.forEach((c) => {
				const item = document.createElement("a");
				item.className = "list-group-item list-group-item-action";
				item.href = "#";
				item.textContent = c.text;
				item.addEventListener("click", (e) => {
					e.preventDefault();
					state.customer = c;
					customerHint();
					qs("#customerResults").classList.add("d-none");
				});
				list.appendChild(item);
			});
			list.classList.remove("d-none");
		} catch (_) {}
	};

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
		const cur = selectedCurrency();
		const rate = currentRate() || 1;
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

	const doCheckout = async (print = false) => {
		if (checkoutBusy) return;
		checkoutBusy = true;
		try {
			if (state.cart.length === 0) {
				showAlert("السلة فارغة", "warning");
				return;
			}
			if (!state.customer) {
				try {
					const r = await fetch("/pos/api/walkin-customer");
					const d = await r.json();
					if (d.success) state.customer = d;
				} catch (_e) {
					showAlert("تعذر اختيار عميل نقدي");
					return;
				}
			}
			await recalc();
			const lines = state.cart.map((it) => ({
				product_id: it.productId,
				quantity: it.qty,
				unit_price: it.price,
				discount_percent: it.discountPercent || 0,
			}));
			const body = {
				idempotency_key: state.idemKey,
				customer_id: state.customer?.id,
				quick_customer: true,
				warehouse_id: qs("#warehouseId")?.value || null,
				currency: selectedCurrency(),
				exchange_rate: currentRate() || 1,
				tax_rate: toNum(qs("#taxRate")?.value) || 0,
				shipping_cost: toNum(qs("#shippingCost")?.value) || 0,
				discount_amount: toNum(qs("#discountAmount")?.value) || 0,
				payment_method: qs("#paymentMethod")?.value || "",
				paid_amount: toNum(qs("#paidAmount")?.value) || 0,
				payment_currency: selectedCurrency(),
				payment_exchange_rate: currentRate() || 1,
				reference_number: qs("#referenceNumber")?.value || "",
				order_type: qs("#orderType")?.value || null,
				table_id:
					qs("#tableSelect") && !qs("#tableField")?.classList.contains("d-none")
						? qs("#tableSelect").value || null
						: null,
				lines: lines,
			};
			if (splitEnabled()) {
				const chunks = readSplitPayments();
				if (!chunks) return;
				body.payments = chunks;
			}
			try {
				const sendCheckout = (token) => {
					const payload = token ? { ...body, override_token: token } : body;
					return fetch("/pos/api/checkout", {
						method: "POST",
						headers: {
							"Content-Type": "application/json",
							"X-CSRFToken": csrf,
							"Idempotency-Key": state.idemKey,
						},
						body: JSON.stringify(payload),
					});
				};
				let r = await sendCheckout(null);
				let d = await r.json().catch(() => ({}));
				if (needsOverride(r, d)) {
					const token = await requestOverrideToken("discount_override");
					if (token) {
						r = await sendCheckout(token);
						d = await r.json().catch(() => ({}));
					}
				}
				if (r.status === 202 && d.queued) {
					// SW queued the sale offline — accepted locally, not an error.
					showAlert(
						d.message || "تم حفظ الفاتورة محلياً وستُرسل تلقائياً عند عودة الاتصال.",
						"warning",
					);
					if (window.printQueuedCartReceipt) {
						void printQueuedCartReceipt(state.cart, state.lastTotals, body);
					}
					state.cart = [];
					state.idemKey = newCartKey();
					await renderCart();
					const splitToggle = qs("#splitTenderToggle");
					if (splitToggle) splitToggle.checked = false;
					qs("#splitTenderBox")?.classList.add("d-none");
					const splitRows = qs("#splitTenderRows");
					if (splitRows) splitRows.innerHTML = "";
					return;
				}
				if (d.success) {
					qs("#doneSaleNumber").textContent = d.sale_number;
					renderUpsellMessages(qs("#doneUpsellList"), d.upsell_prompts);
					qs("#doneViewBtn").href = d.view_url;
					qs("#donePrintBtn").href = d.print_url;
					$("#posDoneModal").modal("show");
					state.cart = [];
					state.idemKey = newCartKey();
					await renderCart();
					const splitToggle = qs("#splitTenderToggle");
					if (splitToggle) splitToggle.checked = false;
					qs("#splitTenderBox")?.classList.add("d-none");
					const splitRows = qs("#splitTenderRows");
					if (splitRows) splitRows.innerHTML = "";
					if (print) {
						window.open(d.print_url, "_blank");
					}
				} else {
					showAlert(d.error || "فشل حفظ الفاتورة");
				}
			} catch (_) {
				showAlert("فشل الاتصال بالخادم");
			}
		} catch (_) {
			showAlert("فشل الاتصال بالخادم");
		} finally {
			checkoutBusy = false;
		}
	};

	document.addEventListener("DOMContentLoaded", () => {
		void loadCategories();
		void loadProducts();
		void loadOrderTypes();
		initSession();

		qs("#posPinConfirm")?.addEventListener("click", () => void confirmPin());
		qs("#posPinInput")?.addEventListener("keydown", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				void confirmPin();
			}
		});
		$("#posPinModal").on("hidden.bs.modal", () => settlePin(null));
		qs("#splitTenderToggle")?.addEventListener("change", (e) => {
			const box = qs("#splitTenderBox");
			box?.classList.toggle("d-none", !e.target.checked);
			if (e.target.checked && !qsa("#splitTenderRows .split-row").length) {
				addSplitRow(qs("#kpiTotal")?.textContent || "", qs("#paymentMethod")?.value || "cash");
			}
		});
		qs("#splitTenderAdd")?.addEventListener("click", () => addSplitRow("", "cash"));
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

		qs("#productSearch").addEventListener("input", (e) => {
			const q = e.target.value.trim();
			clearTimeout(productSearchTimer);
			productSearchTimer = setTimeout(() => void loadProducts(q || ""), 150);
		});
		qs("#productSearch").addEventListener("keydown", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				const q = e.target.value.trim();
				if (q) void loadProducts(q);
			}
		});

		const custSearch = qs("#customerSearch") || qs("#customerSelectedHint");
		if (custSearch && custSearch.id === "customerSearch") {
			let custTimer;
			custSearch.addEventListener("input", (e) => {
				clearTimeout(custTimer);
				const q = e.target.value.trim();
				custTimer = setTimeout(() => searchCustomers(q), 200);
			});
		}
		qs("#walkinCustomer")?.addEventListener("click", () => {
			fetch("/pos/api/walkin-customer")
				.then((r) => r.json())
				.then((d) => {
					if (d.success) {
						state.customer = d;
						customerHint();
					}
				})
				.catch(() => {});
		});
		qs("#clearCustomer")?.addEventListener("click", () => {
			state.customer = null;
			customerHint();
		});

		qsa(".pos-numpad button").forEach((b) => {
			b.addEventListener("click", (e) => {
				handleNumpad(e.currentTarget.dataset.key);
			});
		});

		qs("#checkoutBtn").addEventListener("click", () => doCheckout(false));
		qs("#checkoutPrintBtn")?.addEventListener("click", () => doCheckout(true));
		qs("#clearCartBtn")?.addEventListener("click", () => {
			state.cart = [];
			state.idemKey = newCartKey();
			void renderCart();
		});

		qsa("#taxRate,#shippingCost,#discountAmount,#paidAmount,#paymentMethod,#warehouseId").forEach(
			(el) => {
				if (el) el.addEventListener("change", recalc);
				if (el) el.addEventListener("input", recalc);
			},
		);
		qs("#currency")?.addEventListener("change", loadRateForCurrency);
		qs("#exchangeRate")?.addEventListener("input", updateCartPrices);
		qs("#exchangeRate")?.addEventListener("change", updateCartPrices);
		qs("#warehouseId")?.addEventListener("change", () => {
			const q = qs("#productSearch")?.value?.trim();
			if (q) void loadProducts(q);
		});

		qs("#openSessionBtn").addEventListener("click", () => {
			$("#openSessionModal").modal("show");
		});
		qs("#openSessionConfirm").addEventListener("click", () => {
			if (_sessionBusy) return;
			// Empty field = 0 balance (allowed); garbage text must not silently
			// become 0 (Number("")/Number("abc") both coerce to 0 via toNum).
			const openRaw = qs("#openSessionBalance")?.value ?? "";
			const openingBalance = openRaw.trim() === "" ? 0 : Number(openRaw);
			if (!Number.isFinite(openingBalance)) {
				showAlert("رصيد الافتتاح غير صحيح — أدخل رقماً صحيحاً");
				return;
			}
			_sessionBusy = true;
			const openBtn = qs("#openSessionConfirm");
			openBtn.disabled = true;
			const bal = openingBalance;
			fetch("/pos/api/session/open", {
				method: "POST",
				headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
				body: JSON.stringify({
					opening_balance: bal,
					notes: qs("#openSessionNotes")?.value,
				}),
			})
				.then((r) => r.json())
				.then((d) => {
					if (d.success) {
						$("#openSessionModal").modal("hide");
						initSession();
					} else {
						showAlert(d.error || "فشل فتح الجلسة");
					}
				})
				.catch(() => {})
				.finally(() => {
					_sessionBusy = false;
					openBtn.disabled = false;
				});
		});
		qs("#closeSessionBtn").addEventListener("click", () => {
			fetch("/pos/api/session/report")
				.then((r) => r.json())
				.then((d) => {
					if (d.success && d.session) {
						qs("#closeOpening").textContent = fmt(d.session.opening_balance);
						const canViewSensitive =
							d.session.total_cash_sales !== undefined && d.session.expected_balance !== undefined;
						qs("#closeExpectedBlock").classList.toggle("d-none", !canViewSensitive);
						if (canViewSensitive) {
							qs("#closeCashSales").textContent = fmt(d.session.total_cash_sales);
							qs("#closeExpected").textContent = fmt(d.session.expected_balance);
						}
						$("#closeSessionModal").modal("show");
					}
				})
				.catch(() => {});
		});
		qs("#closeSessionConfirm").addEventListener("click", () => {
			if (_sessionBusy) return;
			const closeRaw = qs("#closeSessionBalance")?.value ?? "";
			const closingBalance = closeRaw.trim() === "" ? 0 : Number(closeRaw);
			if (!Number.isFinite(closingBalance)) {
				showAlert("رصيد الإغلاق غير صحيح — أدخل رقماً صحيحاً");
				return;
			}
			_sessionBusy = true;
			const closeBtn = qs("#closeSessionConfirm");
			closeBtn.disabled = true;
			const bal = closingBalance;
			fetch("/pos/api/session/close", {
				method: "POST",
				headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
				body: JSON.stringify({
					closing_balance: bal,
					notes: qs("#closeSessionNotes")?.value,
				}),
			})
				.then((r) => r.json())
				.then((d) => {
					if (d.success) {
						$("#closeSessionModal").modal("hide");
						initSession();
					} else {
						showAlert(d.error || "فشل إغلاق الجلسة");
					}
				})
				.catch(() => {})
				.finally(() => {
					_sessionBusy = false;
					closeBtn.disabled = false;
				});
		});

		if (window.BarcodeScanner) {
			const handleScannedCode = async (code) => {
				qs("#productSearch").value = code;
				let d = null;
				try {
					const r = await fetch(`/pos/api/product?code=${encodeURIComponent(code)}`);
					d = await r.json();
				} catch (_) {
					// network down — fall through to the offline catalog snapshot
				}
				if ((!d || d.success === false) && window.posOfflineCatalog) {
					d = await posOfflineCatalog.lookupLocalProduct(code);
				}
				if (d && d.success !== false) {
					const liveKg = Number(state.scaleWeightKg) || 0;
					const qty = d.is_weight_product && liveKg > 0 ? liveKg : d.scale_weight_kg || 1;
					void addToCart(d, qty);
					qs("#productSearch").value = "";
				} else {
					showAlert(d?.error || "المنتج غير موجود");
				}
			};
			state.barcodeScanner = new BarcodeScanner({
				onScan: handleScannedCode,
				minLength: 3,
			});
			state.barcodeScanner.start();
			if (window.setupCameraScanUI) {
				setupCameraScanUI({
					button: qs("#cameraScanBtn"),
					onScan: handleScannedCode,
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
		}

		document.addEventListener("keydown", (e) => {
			if (e.target.matches("input,textarea,select") && e.key !== "Escape" && e.key !== "Enter")
				return;
			if (e.key === "Enter" && state.numpadMode) {
				handleNumpad("Enter");
				return;
			}
			if (e.key === "F2") {
				e.preventDefault();
				qs("#productSearch")?.focus();
			}
			if (e.key === "F4") {
				qs("#customerSearch")?.focus();
			}
			if (e.key === "F8") {
				e.preventDefault();
				void doCheckout(true);
			}
			if (e.key === "Escape") {
				state.numpadBuffer = "";
				state.numpadMode = null;
			}
		});
	});
})();
