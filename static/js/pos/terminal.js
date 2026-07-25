/**
 * Push-to-terminal card payments for the POS register.
 *
 * Backend mints the connection token + card_present PaymentIntent; this
 * module lazily loads Stripe's Terminal SDK, connects to the paired reader
 * (reader id remembered in localStorage), collects and processes the payment.
 * Any failure raises an Arabic user-safe error and the cashier keeps the
 * manual card flow — settlement posting is unchanged.
 */
/* global StripeTerminal */

const _TERMINAL_SDK_URL = "https://js.stripe.com/terminal/v1/";
const _READER_STORAGE_KEY = "pos.terminal.reader_id";
// Stripe charges default to the tenant's base currency (POS templates expose it
// via meta), never a hardcoded code.
const _DEFAULT_CURRENCY =
	document.querySelector('meta[name="pos-base-currency"]')?.getAttribute("content") ||
	window._FX_FALLBACK_BASE ||
	"ILS";
let _sdkPromise = null;

function _loadTerminalSdk() {
	if (window.StripeTerminal) return Promise.resolve();
	if (_sdkPromise) return _sdkPromise;
	_sdkPromise = new Promise((resolve, reject) => {
		const s = document.createElement("script");
		s.src = _TERMINAL_SDK_URL;
		s.onload = () => resolve();
		s.onerror = () => {
			_sdkPromise = null;
			reject(new Error("تعذر تحميل مكتبة الدفع الطرفي. تحقق من الاتصال."));
		};
		document.head.appendChild(s);
	});
	return _sdkPromise;
}

async function _postJson(url, body) {
	const res = await fetch(url, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body || {}),
	});
	const data = await res.json().catch(() => ({}));
	if (!res.ok || data.success === false) {
		throw new Error(data.error || "فشلت عملية الدفع الطرفي.");
	}
	return data;
}

class PosTerminal {
	constructor({ baseUrl = "" } = {}) {
		this.baseUrl = baseUrl;
		this._terminal = null;
		this._reader = null;
	}

	async checkStatus() {
		try {
			const res = await fetch(`${this.baseUrl}/pos/api/terminal/status`);
			const data = await res.json().catch(() => ({}));
			return !!(res.ok && data.success && data.configured);
		} catch {
			return false;
		}
	}

	async _getTerminal() {
		if (this._terminal) return this._terminal;
		await _loadTerminalSdk();
		this._terminal = StripeTerminal.create({
			onFetchConnectionToken: async () => {
				const data = await _postJson(`${this.baseUrl}/pos/api/terminal/connection_token`);
				return data.secret;
			},
			onUnexpectedReaderDisconnect: () => {
				this._reader = null;
			},
		});
		return this._terminal;
	}

	async _connectReader(terminal) {
		if (this._reader) return this._reader;
		const savedId = localStorage.getItem(_READER_STORAGE_KEY);
		const discovered = await terminal.discoverReaders();
		if (discovered.error) throw new Error("تعذر البحث عن قارئ البطاقات.");
		const readers = discovered.discoveredReaders || [];
		if (readers.length === 0) throw new Error("لا يوجد قارئ بطاقات مقترن. استخدم الدفع اليدوي.");
		const reader = readers.find((r) => r.id === savedId) || readers[0];
		const connected = await terminal.connectReader(reader);
		if (connected.error) throw new Error("تعذر الاتصال بقارئ البطاقات.");
		this._reader = connected.reader;
		localStorage.setItem(_READER_STORAGE_KEY, this._reader.id || "");
		return this._reader;
	}

	/**
	 * Push a card charge to the reader. Resolves with the processed
	 * PaymentIntent id on approval; throws an Arabic user-safe Error
	 * otherwise (caller falls back to the manual card flow).
	 */
	async pushPayment({ amount, currency = _DEFAULT_CURRENCY, saleReference = "" }) {
		const intent = await _postJson(`${this.baseUrl}/pos/api/terminal/payment_intent`, {
			amount: String(amount),
			currency,
			sale_reference: saleReference,
		});
		const terminal = await this._getTerminal();
		await this._connectReader(terminal);
		const collected = await terminal.collectPaymentMethod(intent.client_secret);
		if (collected.error) throw new Error("ألغيت العملية أو تعذرت قراءة البطاقة.");
		const processed = await terminal.processPayment(collected.paymentIntent);
		if (processed.error) throw new Error("رفضت جهة الإصدار العملية. استخدم الدفع اليدوي.");
		const paid = processed.paymentIntent;
		if (paid?.status !== "succeeded") {
			throw new Error("لم تكتمل عملية الدفع. استخدم الدفع اليدوي.");
		}
		return { intentId: paid.id || intent.id, amountMinor: intent.amount_minor };
	}
}

/**
 * Wire the push-to-terminal button. The button stays hidden unless the
 * provider is configured; on approval the paid amount field is filled with
 * the exact total so the normal (manual-path) checkout posts settlement.
 */
async function setupTerminalButton({ button, getAmount, getCurrency, onApproved, onError }) {
	if (!button) return null;
	const terminal = new PosTerminal({});
	const configured = await terminal.checkStatus();
	if (!configured) return null;
	button.classList.remove("d-none");
	button.addEventListener("click", async () => {
		const amount = Number(getAmount?.() || 0);
		if (!(amount > 0)) {
			onError?.("أضف أصنافاً إلى السلة أولاً.");
			return;
		}
		button.disabled = true;
		try {
			const result = await terminal.pushPayment({
				amount,
				currency: getCurrency?.() || _DEFAULT_CURRENCY,
			});
			onApproved?.(result);
		} catch (err) {
			onError?.(err?.message || "فشلت عملية الدفع الطرفي.");
		} finally {
			button.disabled = false;
		}
	});
	return terminal;
}

window.PosTerminal = PosTerminal;
window.setupTerminalButton = setupTerminalButton;
