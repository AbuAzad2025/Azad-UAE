const t = window.t || ((k) => k);
const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
const state = {
	customer: null,
	cart: [],
	lastProductResults: [],
	barcodeScanner: null,
	selectedTable: null,
};
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
const esc = (s) => {
	if (s == null) return "";
	return String(s)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");
};
const pricesIncludeVatMeta =
	document.querySelector('meta[name="pos-prices-include-vat"]')?.getAttribute("content") === "true";
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
const tenantPosSymbol = document
	.querySelector('meta[name="pos-currency-symbol"]')
	?.getAttribute("content");
if (baseCurrency && tenantPosSymbol) CURRENCY_SYMBOLS[baseCurrency] = tenantPosSymbol;
const currencySymbolFor = (code) => CURRENCY_SYMBOLS[code] || code;
const warehouseParam = (sep = "&") => {
	const el = qs("#warehouseId");
	const w = el ? String(el.value || "").trim() : "";
	return w ? `${sep}warehouse_id=${encodeURIComponent(w)}` : "";
};
const _unwrapEnvelope = (payload) => {
	if (
		payload &&
		typeof payload === "object" &&
		!Array.isArray(payload) &&
		"success" in payload &&
		"data" in payload
	) {
		return payload.data;
	}
	return payload;
};
const fetchJson = async (url) => {
	const r = await fetch(url, {
		credentials: "same-origin",
		headers: { Accept: "application/json" },
	});
	const raw = await r.json().catch(() => null);
	// 404 is a valid business case for product lookup — surface the translated message
	if (r.status === 404) {
		const msg =
			(raw && (raw.message || raw.error)) ||
			(raw?.data && (raw.data.message || raw.data.error)) ||
			"غير موجود";
		return { ok: false, error: String(msg) };
	}
	if (!r.ok) {
		const msg =
			(raw && (raw.message || raw.error)) ||
			(raw?.data && (raw.data.message || raw.data.error)) ||
			`HTTP ${r.status}`;
		return { ok: false, error: String(msg) };
	}
	// Success envelope: {success:true, data:...} — unwrap to inner data for callers.
	// Raw arrays (legacy test mocks) and plain objects pass through unchanged.
	if (raw && typeof raw === "object" && "success" in raw) {
		if (!raw.success) {
			const msg = raw.message || raw.error || `HTTP ${r.status}`;
			return { ok: false, error: String(msg) };
		}
		return { ok: true, data: _unwrapEnvelope(raw) };
	}
	return { ok: true, data: raw };
};

export {
	baseCurrency,
	CURRENCY_SYMBOLS,
	csrf,
	currencySymbolFor,
	currentRate,
	esc,
	fetchJson,
	fmt,
	newCartKey,
	priceForCurrency,
	pricesIncludeVatMeta,
	qs,
	qsa,
	selectedCurrency,
	state,
	t,
	toNum,
	warehouseParam,
};
