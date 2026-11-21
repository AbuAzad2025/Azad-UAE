// Cashier toolkit: the register actions that already exist on the server but
// had no visible control — session report, drawer movements, returns, stock
// lookup, fast-cash keys and hardware status. Every action reuses an existing
// API; this module only renders and posts, it never computes money itself.

import { recalc } from "./cart.js";
import {
	csrf,
	esc,
	fetchJson,
	fmt,
	qs,
	qsa,
	selectedCurrency,
	sessionHeaders,
	state,
	toNum,
} from "./core.js";
import { requestOverrideToken } from "./payments.js";
import { showAlert } from "./ui.js";

const t = (s) => (window.t ? window.t(s) : s);
const modal = (id) => (window.$ ? window.$(`#${id}`) : null);

const byId = (id) => qs(id.startsWith("#") ? id : `#${id}`);
const alertIn = (id, message, level = "danger") => {
	const el = byId(id);
	if (!el) return;
	el.textContent = message || "";
	el.classList.remove("d-none", "alert-danger", "alert-success", "alert-warning");
	el.classList.add(`alert-${level}`);
};
const clearAlert = (id) => {
	const el = byId(id);
	if (!el) return;
	el.textContent = "";
	el.classList.add("d-none");
};

// POST with the POS session token and an optional supervisor override.
const postAuthed = async (url, body, action) => {
	const send = async (token) => {
		const payload = token ? { ...body, override_token: token } : body;
		const r = await fetch(url, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-CSRFToken": csrf,
				...sessionHeaders(),
			},
			credentials: "same-origin",
			body: JSON.stringify(payload),
		});
		const j = await r.json().catch(() => ({}));
		return { r, j };
	};
	let out = await send(null);
	if (out.r.status === 403 && action) {
		const token = await requestOverrideToken(action);
		if (token) out = await send(token);
	}
	return out;
};

const row = (label, value) =>
	`<div class="pos-report-row"><span>${esc(label)}</span><b>${esc(value)}</b></div>`;

// ---------- Session report (the modal existed but had no opener) ----------
const openSessionReport = async () => {
	const body = qs("#sessionReportBody");
	if (!body) return;
	body.innerHTML = `<div class="text-center py-3"><i class="fas fa-spinner fa-spin" aria-hidden="true"></i> ${t("جاري التحميل...")}</div>`;
	const res = await fetchJson("/pos/api/session/report");
	const s = res.data?.session;
	if (!res.ok || !s) {
		body.innerHTML = `<div class="alert alert-info mb-0">${esc(res.error || t("لا توجد جلسة مفتوحة."))}</div>`;
		return;
	}
	let html = row(t("رقم الجلسة"), s.number || "—");
	html += row(t("الحالة"), s.status === "open" ? t("مفتوحة") : t("مغلقة"));
	html += row(t("رصيد الافتتاح"), fmt(s.opening_balance));
	html += row(t("مدة الجلسة"), `${s.duration_minutes || 0} ${t("دقيقة")}`);
	html += row(t("الفرع"), s.branch_id || "—");
	if (s.expected_balance !== undefined) {
		html += row(t("إجمالي المبيعات"), fmt(s.total_sales));
		html += row(t("مبيعات نقدية"), fmt(s.total_cash_sales));
		html += row(t("مبيعات بطاقة"), fmt(s.total_card_sales));
		html += row(t("الباقي الموضوع"), fmt(s.total_change_given));
		html += row(t("إيداعات"), fmt(s.total_pay_ins));
		html += row(t("مصروفات"), fmt(s.total_pay_outs));
		html += row(t("الرصيد المتوقع"), fmt(s.expected_balance));
		if (s.closing_balance !== null && s.closing_balance !== undefined) {
			html += row(t("الرصيد المعدود"), fmt(s.closing_balance));
			html += row(t("الفرق"), fmt(s.difference));
		}
	}
	if (s.notes) html += row(t("ملاحظات"), s.notes);
	body.innerHTML = html;
	modal("sessionReportModal")?.modal("show");
};

// ---------- Drawer cash movements ----------
const loadCashMovements = async () => {
	const box = qs("#cashMovementsList");
	if (!box) return;
	const res = await fetchJson("/pos/api/cash-movements?limit=8");
	if (!res.ok) {
		box.innerHTML = `<div class="text-muted small">${esc(res.error || "")}</div>`;
		return;
	}
	const items = res.data?.movements || [];
	if (!items.length) {
		box.innerHTML = `<div class="text-muted small">${t("لا توجد حركات بعد")}</div>`;
		return;
	}
	box.innerHTML = items
		.map((m) => {
			const incoming = m.movement_type === "pay_in" || m.type === "pay_in";
			const sign = incoming ? "+" : "−";
			const label = incoming ? t("إيداع") : t("صرف");
			return `<div class="pos-mini-row"><span class="${incoming ? "pos-in" : "pos-out"}">${sign} ${esc(label)}</span><b>${fmt(m.amount)}</b><small>${esc(m.reason || m.created_at || "")}</small></div>`;
		})
		.join("");
};

const openCashMovements = async () => {
	clearAlert("cashMovementAlert");
	qs("#cashMovementAmount").value = "0";
	qs("#cashMovementReason").value = "";
	await loadCashMovements();
	modal("cashMovementModal")?.modal("show");
};

const saveCashMovement = async () => {
	const amount = toNum(qs("#cashMovementAmount").value);
	if (!(amount > 0)) {
		alertIn("cashMovementAlert", t("أدخل مبلغاً صحيحاً"), "warning");
		return;
	}
	const type = qs("#cashMovementType").value;
	const body = {
		type,
		amount,
		reason: qs("#cashMovementReason").value.trim(),
	};
	const { r, j } = await postAuthed("/pos/api/cash-movements", body, type);
	if (!r.ok || !j.success) {
		alertIn("cashMovementAlert", j.message || j.error || t("تعذر تسجيل الحركة"));
		return;
	}
	showAlert(t("تم تسجيل الحركة"), "success");
	await loadCashMovements();
	qs("#cashMovementAmount").value = "0";
	qs("#cashMovementReason").value = "";
};

// ---------- Returns ----------
let currentReceipt = null;

const openReturns = () => {
	clearAlert("returnAlert");
	qs("#returnReceiptNumber").value = "";
	qs("#returnReceiptInfo").classList.add("d-none");
	qs("#returnLines").innerHTML = "";
	currentReceipt = null;
	modal("returnsModal")?.modal("show");
	qs("#returnReceiptNumber").focus();
};

const lookupReceipt = async () => {
	const number = qs("#returnReceiptNumber").value.trim();
	if (!number) {
		alertIn("returnAlert", t("أدخل رقم الإيصال"), "warning");
		return;
	}
	clearAlert("returnAlert");
	const res = await fetchJson(`/pos/api/receipts/lookup?number=${encodeURIComponent(number)}`);
	if (!res.ok || !res.data?.receipt) {
		currentReceipt = null;
		qs("#returnLines").innerHTML = "";
		qs("#returnReceiptInfo").classList.add("d-none");
		alertIn("returnAlert", res.error || t("الإيصال غير موجود"));
		return;
	}
	currentReceipt = res.data.receipt;
	const r = currentReceipt;
	const info = qs("#returnReceiptInfo");
	info.innerHTML =
		row(t("رقم الفاتورة"), r.sale_number) +
		row(t("الزبون"), r.customer_name || "—") +
		row(t("الإجمالي"), fmt(r.total_amount)) +
		row(t("العملة"), r.currency || "—");
	info.classList.remove("d-none");
	qs("#returnLines").innerHTML = (r.lines || [])
		.filter((line) => Number(line.quantity_returnable) > 0)
		.map(
			(line, i) => `<div class="pos-return-line">
        <div class="rl-name">${esc(line.product_name || line.sku || line.product_id)}</div>
        <div class="rl-meta">${t("المباع")}: ${fmt(line.quantity_sold)} · ${t("المتبقي للإرجاع")}: ${fmt(line.quantity_returnable)} · ${fmt(line.unit_price)}</div>
        <input type="number" class="form-control form-control-sm rl-qty" data-i="${i}" data-line="${line.sale_line_id}" min="0" max="${line.quantity_returnable}" step="0.001" value="0">
      </div>`,
		)
		.join("");
};

const submitReturn = async () => {
	if (!currentReceipt) {
		alertIn("returnAlert", t("ابحث عن الإيصال أولاً"), "warning");
		return;
	}
	const lines = qsa("#returnLines .rl-qty")
		.map((input) => ({
			sale_line_id: Number(input.dataset.line),
			quantity: toNum(input.value),
		}))
		.filter((line) => line.quantity > 0);
	if (!lines.length) {
		alertIn("returnAlert", t("حدد أصنافاً للإرجاع"), "warning");
		return;
	}
	const body = {
		sale_id: currentReceipt.sale_id,
		sale_number: currentReceipt.sale_number,
		lines,
		refund_method: qs("#returnRefundMethod").value,
		notes: qs("#returnNotes").value.trim(),
	};
	const { r, j } = await postAuthed("/pos/api/returns", body, "pos_return");
	if (!r.ok || !j.success) {
		alertIn("returnAlert", j.message || j.error || t("تعذر تسجيل المرتجع"));
		return;
	}
	showAlert(t("تم تسجيل المرتجع"), "success");
	modal("returnsModal")?.modal("hide");
	await lookupReceipt();
};

// ---------- Stock lookup ----------
const openStockLookup = () => {
	clearAlert("stockLookupAlert");
	qs("#stockLookupResult").innerHTML = "";
	modal("stockLookupModal")?.modal("show");
	qs("#stockLookupQuery").focus();
};

const runStockLookup = async () => {
	const q = qs("#stockLookupQuery").value.trim();
	if (!q) {
		alertIn("stockLookupAlert", t("أدخل باركود أو رقم صنف"), "warning");
		return;
	}
	clearAlert("stockLookupAlert");
	const param = /^\d+$/.test(q) ? "product_id" : "barcode";
	const res = await fetchJson(`/pos/api/stock/lookup?${param}=${encodeURIComponent(q)}`);
	if (!res.ok || !res.data) {
		alertIn("stockLookupAlert", res.error || t("المنتج غير موجود"));
		qs("#stockLookupResult").innerHTML = "";
		return;
	}
	const d = res.data;
	let html = row(t("المنتج"), d.product_name || d.name || q);
	const breakdown = d.warehouses || d.stock || d.breakdown || [];
	if (Array.isArray(breakdown) && breakdown.length) {
		html += breakdown
			.map((w) =>
				row(w.warehouse_name || w.name || "—", fmt(w.quantity ?? w.stock ?? w.on_hand ?? 0)),
			)
			.join("");
	} else {
		html += row(t("الكمية"), fmt(d.quantity ?? d.on_hand ?? d.total ?? 0));
	}
	qs("#stockLookupResult").innerHTML = html;
};

// ---------- Fast cash keys ----------
let fastCashTimer = null;
const renderFastCash = async () => {
	const box = qs("#posFastCash");
	if (!box) return;
	const total = toNum(state.lastTotals?.total);
	if (!(total > 0)) {
		box.innerHTML = "";
		return;
	}
	const res = await fetchJson(
		`/pos/api/fast-cash?total=${encodeURIComponent(total)}&currency=${encodeURIComponent(selectedCurrency())}`,
	);
	if (!res.ok || !res.data?.options) {
		box.innerHTML = "";
		return;
	}
	box.innerHTML = res.data.options
		.map(
			(o) =>
				`<button type="button" class="pos-fast-key${o.is_exact ? " exact" : ""}" data-amount="${o.amount}" title="${t("الباقي")}: ${fmt(o.change)}">${fmt(o.amount)}</button>`,
		)
		.join("");
};
const scheduleFastCash = () => {
	clearTimeout(fastCashTimer);
	fastCashTimer = setTimeout(() => void renderFastCash(), 250);
};

// ---------- Hardware status badge ----------
const refreshHardwareStatus = async () => {
	const badge = qs("#hardwareStatusBadge");
	if (!badge) return;
	const res = await fetchJson("/pos/api/hardware/status");
	const stateName = res.data?.status || "disconnected";
	badge.dataset.state = stateName;
	badge.title = `${t("حالة الأجهزة")}: ${stateName}`;
};

const setupPosToolkit = () => {
	// SaaS-gated actions stay out of sight on plans that do not include them;
	// the server remains the authority (the APIs still refuse them).
	const cfg = window.POS_CONFIG || {};
	const gate = (selector, enabled) => {
		const button = qs(selector);
		if (!button || enabled !== false) return;
		button.setAttribute("disabled", "disabled");
		button.classList.add("disabled");
		button.title = t("متاح في الباقة الاحترافية");
	};
	gate("#returnsBtn", cfg.enable_pos_returns);
	gate("#cashMovementBtn", cfg.enable_pos_shifts);

	qs("#customerDisplayBtn")?.addEventListener("click", () => {
		if (!state.customerDisplayUrl) {
			showAlert(t("افتح جلسة كاشير أولاً"), "warning");
			return;
		}
		window.open(state.customerDisplayUrl, "_blank", "noopener,noreferrer");
	});
	qs("#sessionReportBtn")?.addEventListener("click", () => void openSessionReport());
	qs("#cashMovementBtn")?.addEventListener("click", () => void openCashMovements());
	qs("#cashMovementSave")?.addEventListener("click", () => void saveCashMovement());
	qs("#returnsBtn")?.addEventListener("click", openReturns);
	qs("#returnLookupBtn")?.addEventListener("click", () => void lookupReceipt());
	qs("#returnReceiptNumber")?.addEventListener("keydown", (e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			void lookupReceipt();
		}
	});
	qs("#returnSubmitBtn")?.addEventListener("click", () => void submitReturn());
	qs("#stockLookupBtn")?.addEventListener("click", openStockLookup);
	qs("#stockLookupGo")?.addEventListener("click", () => void runStockLookup());
	qs("#stockLookupQuery")?.addEventListener("keydown", (e) => {
		if (e.key === "Enter") {
			e.preventDefault();
			void runStockLookup();
		}
	});

	qs("#posFastCash")?.addEventListener("click", (e) => {
		const key = e.target.closest("button[data-amount]");
		if (!key) return;
		const paid = qs("#paidAmount");
		if (paid) paid.value = key.dataset.amount;
		void recalc();
	});
	const paid = qs("#paidAmount");
	paid?.addEventListener("input", scheduleFastCash);
	window.addEventListener("pos:totals", scheduleFastCash);

	// Re-render fast keys whenever the cart total changes (recalc dispatches
	// pos:totals in cart.js; the paid-input listener covers manual entry).
	void renderFastCash();
	void refreshHardwareStatus();
	window.setInterval(() => void refreshHardwareStatus(), 60000);
};

export {
	loadCashMovements,
	lookupReceipt,
	openCashMovements,
	openReturns,
	openSessionReport,
	openStockLookup,
	refreshHardwareStatus,
	renderFastCash,
	runStockLookup,
	saveCashMovement,
	setupPosToolkit,
	submitReturn,
};
