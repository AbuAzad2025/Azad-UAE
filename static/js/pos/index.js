import {
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
} from "./cart.js";
import {
	baseCurrency,
	csrf,
	currencySymbolFor,
	currentRate,
	esc,
	fetchJson,
	fmt,
	newCartKey,
	priceForCurrency,
	qs,
	qsa,
	selectedCurrency,
	sessionHeaders,
	state,
	toNum,
	warehouseParam,
} from "./core.js";
import { handleScannedCode, setupDevices } from "./offline-sync.js";
import {
	addSplitRow,
	confirmPin,
	needsOverride,
	postWithOverride,
	readSplitPayments,
	requestOverrideToken,
	settlePin,
	splitEnabled,
	splitSumRefresh,
	syncPay,
} from "./payments.js";
import { autoPrintQueuedReceipt, autoPrintSale } from "./printer.js";
import {
	addFirstOrLookup,
	customerHint,
	hideModalAlert,
	loadCategories,
	loadFloors,
	loadOrderTypes,
	loadProducts,
	loadTableOptions,
	loadTables,
	renderProductResults,
	runProductSearch,
	showAlert,
	showModalAlert,
	toggleTableField,
} from "./ui.js";

qs("#cartBody").addEventListener("click", (e) => {
	const btn = e.target.closest("button[data-act]");
	if (!btn) return;
	const idx = Number(btn.getAttribute("data-i"));
	if (!Number.isFinite(idx) || !state.cart[idx]) return;
	const act = btn.getAttribute("data-act");
	if (act === "inc") {
		if (state.cart[idx].serial) {
			showAlert(window.t("المنتج المتسلسل يُباع بوحدة واحدة لكل رقم تسلسلي"), "warning");
			return;
		}
		state.cart[idx].qty = Number(state.cart[idx].qty) + 1;
	}
	if (act === "dec") {
		const nq = Number(state.cart[idx].qty) - 1;
		if (nq <= 0) {
			state.cart.splice(idx, 1);
			state.idemKey = newCartKey();
		} else {
			state.cart[idx].qty = nq;
		}
	}
	void renderCart();
});
qs("#cartBody").addEventListener("input", (e) => {
	const t = e.target;
	const idx = Number(t.getAttribute("data-i"));
	const k = t.getAttribute("data-k");
	if (!Number.isFinite(idx) || !state.cart[idx]) return;
	if (k === "qty") {
		if (state.cart[idx].serial) {
			t.value = 1;
			state.cart[idx].qty = 1;
		} else {
			state.cart[idx].qty = Math.max(0.001, toNum(t.value));
		}
	}
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
qs("#clearCartBtn")?.addEventListener("click", () => {
	if (!confirm(window.t("تفريغ السلة بالكامل؟"))) return;
	state.cart = [];
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
	else {
		// No active search query → reload the grid for the selected warehouse/category
		const activeCat = document.querySelector("#posCategories .pos-cat.active");
		const catId = activeCat ? activeCat.getAttribute("data-cat") : "";
		void loadProducts(catId || "");
		// Re-hydrate offline catalog for the new warehouse filter
		if (window.posOfflineCatalog) {
			void window.posOfflineCatalog.hydrateCatalog({ warehouseParam: warehouseParam("?") });
		}
	}
});
qs("#clearProductSearch").addEventListener("click", () => {
	qs("#productSearch").value = "";
	qs("#productResults").classList.add("d-none");
	state.lastProductResults = [];
});

qs("#posPinConfirm")?.addEventListener("click", () => void confirmPin());
qs("#posPinInput")?.addEventListener("keydown", (e) => {
	if (e.key === "Enter") {
		e.preventDefault();
		void confirmPin();
	}
});
window.$("#posPinModal").on("hidden.bs.modal", () => settlePin(null));
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
			showAlert(j.message || j.error || "تعذر فتح الدرج", "warning");
		}
	} catch (_) {
		showAlert("فشل الاتصال بالخادم", "warning");
	}
});

qs("#splitTenderToggle")?.addEventListener("change", (e) => {
	const box = qs("#splitTenderBox");
	box?.classList.toggle("d-none", !e.target.checked);
	if (e.target.checked && !qsa("#splitTenderRows .split-row").length) {
		addSplitRow(qs("#kpiTotal")?.textContent || "", qs("#paymentMethod")?.value || "cash");
	}
});
qs("#splitTenderAdd")?.addEventListener("click", () => addSplitRow("", "cash"));

let checkoutBusy = false;
const resetAfterSale = async () => {
	state.cart = [];
	state.idemKey = newCartKey();
	await renderCart();
	qs("#paidAmount").value = 0;
	const splitToggle = qs("#splitTenderToggle");
	if (splitToggle) splitToggle.checked = false;
	qs("#splitTenderBox")?.classList.add("d-none");
	const splitRows = qs("#splitTenderRows");
	if (splitRows) splitRows.innerHTML = "";
	qs("#paymentMethod").value = "cash";
	qs("#referenceNumber").value = "";
	if (qs("#orderNote")) qs("#orderNote").value = "";
	if (typeof syncPay === "function") syncPay();
};
const checkout = async (autoPrint) => {
	if (checkoutBusy) return;
	if (!state.customer) {
		try {
			const res = await fetchJson("/pos/api/walkin-customer");
			if (res.ok && res.data) {
				state.customer = res.data;
				qs("#customerSearch").value = res.data.text || res.data.name || "";
				customerHint();
			}
		} catch (_) {}
	}
	if (!state.customer) {
		showAlert("تعذر تحميل عميل نقدي — تحقق من الاتصال.", "warning");
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
		table_id:
			qs("#tableSelect") && !qs("#tableField").classList.contains("d-none")
				? qs("#tableSelect").value || null
				: null,
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
	const serialsByProduct = {};
	state.cart.forEach((it) => {
		if (!it.serial) return;
		if (!serialsByProduct[it.id]) serialsByProduct[it.id] = [];
		serialsByProduct[it.id].push(it.serial);
	});
	if (Object.keys(serialsByProduct).length) payload.serials = serialsByProduct;
	if (payload.payment_method === "cash" && toNum(qs("#paidAmount").value) <= 0) {
		payload.paid_amount = Math.max(0, toNum(_totals?.total));
	}
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
					...sessionHeaders(),
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
		if (r.status === 202 && j.queued) {
			showAlert(j.message || "تم حفظ الفاتورة محلياً وستُرسل تلقائياً عند عودة الاتصال.", "warning");
			void autoPrintQueuedReceipt(state.cart, state.lastTotals, payload);
			await resetAfterSale();
			return;
		}
		if (!r.ok || !j.success) {
			showAlert(j.message || j.error || `HTTP ${r.status}`);
			return;
		}
		const d = j.data || j;
		qs("#doneSaleNumber").textContent = d.sale_number;
		renderUpsellMessages(qs("#doneUpsellList"), d.upsell_prompts);
		qs("#doneViewBtn").href = d.view_url;
		qs("#donePrintBtn").href = d.print_url;
		window.$("#posDoneModal").modal("show");
		autoPrintSale(d.sale_id);
		if (autoPrint) {
			window.open(d.print_url, "_blank", "noopener");
		}
		await resetAfterSale();
		if (state.selectedTable && j.sale_id) {
			try {
				await fetch(`/pos/api/tables/${state.selectedTable.id}/assign`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"X-CSRFToken": csrf,
					},
					credentials: "same-origin",
					body: JSON.stringify({ sale_id: j.sale_id }),
				});
			} catch (_) {}
			state.selectedTable = null;
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

setupDevices();

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
		} else if (act === "total") {
			cur = String(state.lastTotals?.total ?? toNum(cur));
		}
		paidEl.value = cur;
		if (typeof recalc === "function") recalc();
	});
	paidEl.addEventListener("input", recalc);
}

const paySel = qs("#paymentMethod");
qsa("#posPayMethod .pm").forEach((pm) => {
	const selectMethod = () => {
		if (paySel) paySel.value = pm.getAttribute("data-method");
		syncPay();
	};
	pm.addEventListener("click", selectMethod);
	pm.addEventListener("keydown", (e) => {
		if (e.key === "Enter" || e.key === " ") {
			e.preventDefault();
			selectMethod();
		}
	});
});
if (paySel) paySel.addEventListener("change", syncPay);
if (paySel) paySel.value = paySel.value || "cash";
syncPay();

if (window.setupTerminalButton) {
	void window.setupTerminalButton({
		button: qs("#pushTerminalBtn"),
		getAmount: () => state.lastTotals?.total || 0,
		getCurrency: () => selectedCurrency(),
		onApproved: (result) => {
			if (paidEl && state.lastTotals) paidEl.value = String(state.lastTotals.total);
			showAlert(`${window.t("تمت الموافقة على الدفع بالبطاقة")} (${result.intentId})`, "success");
		},
		onError: (msg) => showAlert(msg, "warning"),
	});
}

void loadCategories();
void loadProducts("");

document.addEventListener("keydown", (e) => {
	if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
		e.preventDefault();
		qs("#productSearch").focus();
	}
});

const POS_CONFIG = window.POS_CONFIG || {
	enable_tables: false,
	enable_hold: true,
};
const tablesBtn = qs("#posTablesBtn");
const holdBtn = qs("#posHoldBtn");
const refreshHoldBadge = () => {
	const n = heldCount();
	const b = qs("#posHoldBtn");
	if (b)
		b.innerHTML = `<i class="fas fa-pause"></i>${n ? `<span class="badge warn">${n}</span>` : ""}`;
};
if (POS_CONFIG.enable_tables && tablesBtn) tablesBtn.classList.remove("d-none");
if (POS_CONFIG.enable_hold && holdBtn) holdBtn.classList.remove("d-none");
refreshHoldBadge();

const orderTypeSel = qs("#orderType");
if (orderTypeSel) orderTypeSel.addEventListener("change", toggleTableField);

if (tablesBtn) {
	tablesBtn.addEventListener("click", async () => {
		try {
			await loadFloors();
		} catch (_) {}
		// Always show the tables modal after attempting to load floors
		if (window.$?.("#posTablesModal").modal) {
			window.$("#posTablesModal").modal("show");
		} else {
			const modal = qs("#posTablesModal");
			if (modal) modal.classList.remove("d-none");
		}
	});
	const clearT = qs("#posTableClear");
	if (clearT)
		clearT.addEventListener("click", () => {
			state.selectedTable = null;
			const sel = qs("#posTableSelected");
			if (sel) sel.textContent = "";
			if (tablesBtn) {
				tablesBtn.title = "إدارة الطاولات";
				tablesBtn.classList.remove("has-selection");
			}
		});
}

if (holdBtn) {
	holdBtn.addEventListener("click", async () => {
		// Resume path: empty cart → try server parked carts first, then local hold
		if (!state.cart.length) {
			// Try server-side parked carts when online
			try {
				const r = await fetch("/pos/api/carts?limit=5", {
					credentials: "same-origin",
					headers: { Accept: "application/json" },
				});
				const j = await r.json().catch(() => ({}));
				const serverCarts = j.data?.carts || j.carts || [];
				if (Array.isArray(serverCarts) && serverCarts.length) {
					const last = serverCarts[serverCarts.length - 1];
					try {
						const rr = await fetch(`/pos/api/carts/${last.id}`, {
							credentials: "same-origin",
							headers: { Accept: "application/json" },
						});
						const jj = await rr.json().catch(() => ({}));
						const detail = jj.data?.cart || jj.cart || jj.data;
						if (detail?.payload) {
							const p =
								typeof detail.payload === "string" ? JSON.parse(detail.payload) : detail.payload;
							state.cart = p.cart || p.lines || [];
							state.customer = p.customer || null;
							state.selectedTable = p.table || null;
							state.idemKey = newCartKey();
							if (qs("#orderNote") && p.note) qs("#orderNote").value = p.note;
							await renderCart();
							customerHint();
							refreshHoldBadge();
							showAlert("تم استئناف الفاتورة المعلّقة (خادم)", "success");
							return;
						}
					} catch (_) {}
				}
			} catch (_) {}
			// Fallback to local hold
			const list = JSON.parse(localStorage.getItem(HOLD_KEY) || "[]");
			if (!list.length) {
				showAlert("لا توجد فواتير معلّقة", "warning");
				return;
			}
			const last = list.pop();
			localStorage.setItem(HOLD_KEY, JSON.stringify(list));
			state.cart = last.cart || [];
			state.idemKey = newCartKey();
			state.customer = last.customer || null;
			state.selectedTable = last.table || null;
			if (qs("#orderNote")) qs("#orderNote").value = last.note || "";
			await renderCart();
			customerHint();
			refreshHoldBadge();
			showAlert("تم استئناف الفاتورة المعلّقة", "success");
			return;
		}
		// Park path: try server first when online, always mirror to local for offline resilience
		const payload = {
			cart: state.cart,
			customer: state.customer,
			table: state.selectedTable,
			note: qs("#orderNote") ? qs("#orderNote").value || "" : "",
			ts: Date.now(),
		};
		let serverParked = false;
		try {
			const r = await fetch("/pos/api/carts/park", {
				method: "POST",
				credentials: "same-origin",
				headers: {
					"Content-Type": "application/json",
					Accept: "application/json",
					"X-CSRFToken": csrf,
				},
				body: JSON.stringify({ payload, label: `Hold ${new Date().toLocaleString("ar-EG")}` }),
			});
			if (r.ok) serverParked = true;
		} catch (_) {}
		// Mirror to localStorage for offline fallback
		const list = JSON.parse(localStorage.getItem(HOLD_KEY) || "[]");
		list.push(payload);
		localStorage.setItem(HOLD_KEY, JSON.stringify(list));
		state.cart = [];
		state.idemKey = newCartKey();
		await renderCart();
		refreshHoldBadge();
		if (qs("#orderNote")) qs("#orderNote").value = "";
		const suffix = serverParked ? "" : " (محلياً)";
		showAlert(
			`${window.t("تم تعليق الفاتورة")} (${heldCount()} ${window.t("معلّقة")})${suffix}`,
			"success",
		);
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
		const s = j.data?.session || j.session;
		if (j.success && s) {
			if (window.cfdBroadcast) cfdBroadcast.setSession(s.id);
			bar.classList.remove("d-none");
			required.classList.add("d-none");
			qs("#sessionNumber").textContent = s.number;
			qs("#sessionBalance").textContent = fmt(s.opening_balance);
			qs("#sessionTotal").textContent = fmt(s.total_sales);
			qs("#sessionTime").textContent =
				`${window.t("مفتوحة منذ")} ${s.duration_minutes} ${window.t("دقيقة")}`;
			if (window.__sesTimer) clearInterval(window.__sesTimer);
			window.__sesTimer = setInterval(() => {
				const el = qs("#sessionTime");
				if (el && s.opened_at) {
					const m = Math.floor((Date.now() - new Date(s.opened_at).getTime()) / 60000);
					el.textContent = `${window.t("مفتوحة منذ")} ${m} ${window.t("دقيقة")}`;
				}
			}, 60000);
			qs("#closeOpening").textContent = fmt(s.opening_balance);
		} else {
			if (window.__sesTimer) {
				clearInterval(window.__sesTimer);
				window.__sesTimer = null;
			}
			if (window.cfdBroadcast) cfdBroadcast.setSession(null);
			bar.classList.add("d-none");
			required.classList.remove("d-none");
		}
	} catch (_) {}
}

qs("#openSessionBtn").addEventListener("click", () => {
	qs("#openSessionBalance").value = "0";
	qs("#openSessionNotes").value = "";
	window.$("#openSessionModal").modal("show");
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
			showModalAlert("openSession", j.message || j.error || "فشل فتح الجلسة", "danger");
			return;
		}
		const openedToken = j.data?.session_token ?? j.session_token;
		if (openedToken) {
			state.sessionToken = openedToken;
			sessionStorage.setItem("posSessionToken", openedToken);
		}
		window.$("#openSessionModal").modal("hide");
		await loadSession();
		const opened = j.data?.session || j.session;
		showAlert(`${window.t("تم فتح الجلسة")} ${opened.number}`, "success");
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
		const rep = j.data?.session || j.session;
		if (j.success && rep) {
			qs("#closeOpening").textContent = fmt(rep.opening_balance);
			const canViewSensitive =
				rep.total_cash_sales !== undefined && rep.expected_balance !== undefined;
			qs("#closeExpectedBlock").classList.toggle("d-none", !canViewSensitive);
			if (canViewSensitive) {
				qs("#closeCashSales").textContent = fmt(rep.total_cash_sales);
				qs("#closeExpected").textContent = fmt(rep.expected_balance);
			}
		}
	} catch (err) {
		showModalAlert(
			"closeSession",
			`${window.t("تعذر تحميل بيانات الجلسة")} ${err.message || window.t("خطأ غير معروف")}`,
			"warning",
		);
	}
	qs("#closeSessionBalance").value = "";
	qs("#closeSessionNotes").value = "";
	window.$("#closeSessionModal").modal("show");
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
			headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": csrf,
				...sessionHeaders(),
			},
			credentials: "same-origin",
			body: JSON.stringify({
				closing_balance: balance,
				notes: notes || undefined,
			}),
		});
		const j = await r.json();
		if (!r.ok || !j.success) {
			showModalAlert("closeSession", j.message || j.error || "فشل إغلاق الجلسة", "danger");
			return;
		}
		state.sessionToken = null;
		sessionStorage.removeItem("posSessionToken");
		window.$("#closeSessionModal").modal("hide");
		await loadSession();
		const closed = j.data?.session || j.session;
		const diff = closed.difference;
		if (Math.abs(diff) > 0.01) {
			showAlert(
				`${window.t("تم إغلاق الجلسة. فرق الرصيد")}: ${fmt(diff)}`,
				diff < 0 ? "danger" : "warning",
			);
		} else {
			showAlert("تم إغلاق الجلسة بنجاح. الرصيد مطابق.", "success");
		}
	} catch (err) {
		showModalAlert("closeSession", err.message, "danger");
	} finally {
		qs("#closeSessionConfirm").disabled = false;
	}
});

window.$("#posDoneModal").on("hidden.bs.modal", () => {
	qs("#productSearch").focus();
});
loadOrderTypes();
void loadSession();

window._posFmt = fmt;
window._posToNum = toNum;
window._posEsc = esc;
window._posPriceForCurrency = priceForCurrency;
window._posCurrencySymbolFor = currencySymbolFor;
window._posState = state;
window._posAddToCart = addToCart;
window._posRenderCart = renderCart;
window._posRecalc = recalc;
window._posRenderProductResults = renderProductResults;
window._posRunProductSearch = runProductSearch;
window._posAddFirstOrLookup = addFirstOrLookup;
window._posShowAlert = showAlert;
window._posShowModalAlert = showModalAlert;
window._posHideModalAlert = hideModalAlert;
window._posCustomerHint = customerHint;
window._posUpdateCartPrices = updateCartPrices;
window._posLoadRateForCurrency = loadRateForCurrency;
window._posSplitEnabled = splitEnabled;
window._posSplitSumRefresh = splitSumRefresh;
window._posAddSplitRow = addSplitRow;
window._posReadSplitPayments = readSplitPayments;
window._posResetAfterSale = resetAfterSale;
window._posCheckout = checkout;
window._posHandleScannedCode = handleScannedCode;
window._posLoadCategories = loadCategories;
window._posLoadProducts = loadProducts;
window._posLoadFloors = loadFloors;
window._posLoadTables = loadTables;
window._posHeldCount = heldCount;
window._posNewCartKey = newCartKey;
window._posFetchJson = fetchJson;
window._posWarehouseParam = warehouseParam;
window._posNeedsOverride = needsOverride;
window._posPostWithOverride = postWithOverride;
window._posRequestOverrideToken = requestOverrideToken;
window._posConfirmPin = confirmPin;
window._posSettlePin = settlePin;
window._posEvaluateUpsell = evaluateUpsell;
window._posScheduleUpsellEval = scheduleUpsellEval;
window._posRenderUpsellMessages = renderUpsellMessages;
window._posToggleTableField = toggleTableField;
window._posLoadTableOptions = loadTableOptions;
window._posSyncPay = syncPay;
