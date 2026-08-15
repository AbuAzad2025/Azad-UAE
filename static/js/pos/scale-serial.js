/**
 * POS Web Serial scale driver.
 *
 * Pure frame parser (testable in Node) plus browser glue that streams live
 * weight from a serial scale. When Web Serial is unavailable the caller
 * keeps using prefix-20 weight-embedded barcodes as the fallback path.
 */
/* global module, navigator, TextDecoder */

const _SCALE_NUMBER_RE = /(-?\d+(?:[.,]\d+)?)/;
const _SCALE_STABLE_READS = 3;
const _SCALE_EPSILON_KG = 0.002;

/**
 * Parse one ASCII frame from a scale into kilograms.
 *
 * Handles common protocols: A&D-style headers (`ST,GS,+  1.234kg`,
 * `US,NT,- 0.500kg`), plain numeric lines (`1.234`, `+0001.234`), and
 * gram-denominated frames (`500g`). Returns
 * ``{ weightKg: number, stable: boolean } | null``.
 */
function parseScaleFrame(line) {
	if (line == null) return null;
	const s = String(line).trim();
	if (!s) return null;
	let stable = true;
	if (/^(ST|US|OL|GS|NT)[,\s]/i.test(s)) {
		stable = !/^(US|OL)/i.test(s);
	}
	const m = s.match(_SCALE_NUMBER_RE);
	if (!m) return null;
	const num = Number(m[1].replace(",", "."));
	if (!Number.isFinite(num) || num < 0) return null;
	let kg = num;
	if (!/kg/i.test(s) && /(?:^|[^k])g\b/i.test(s)) {
		kg = num / 1000;
	}
	return { weightKg: Math.round(kg * 1000) / 1000, stable };
}

class PosScaleSerial {
	constructor({ onStableWeight, onError, baudRate = 9600 } = {}) {
		this.onStableWeight = typeof onStableWeight === "function" ? onStableWeight : null;
		this.onError = typeof onError === "function" ? onError : null;
		this.baudRate = baudRate;
		this.port = null;
		this.reader = null;
		this.connected = false;
		this.lastWeightKg = 0;
		this._pendingKg = 0;
		this._pendingCount = 0;
		this._buffer = "";
	}

	static isSupported() {
		return typeof navigator !== "undefined" && !!navigator.serial;
	}

	async connect() {
		if (!PosScaleSerial.isSupported()) {
			this._fail(t("Web Serial غير مدعوم في هذا المتصفح."));
			return false;
		}
		try {
			this.port = await navigator.serial.requestPort();
			await this.port.open({ baudRate: this.baudRate, dataBits: 8, parity: "none", stopBits: 1 });
			this.connected = true;
			void this._readLoop();
			return true;
		} catch (err) {
			this.connected = false;
			this._fail(err?.message || t("تعذر الاتصال بالميزان."));
			return false;
		}
	}

	async disconnect() {
		this.connected = false;
		try {
			if (this.reader) {
				await this.reader.cancel().catch(() => {});
				this.reader = null;
			}
			if (this.port) {
				await this.port.close().catch(() => {});
				this.port = null;
			}
		} finally {
			this.lastWeightKg = 0;
			this._pendingCount = 0;
		}
	}

	async _readLoop() {
		while (this.connected && this.port?.readable) {
			this.reader = this.port.readable.getReader();
			const decoder = new TextDecoder();
			try {
				for (;;) {
					const { value, done } = await this.reader.read();
					if (done) break;
					if (value) this._ingest(decoder.decode(value, { stream: true }));
				}
			} catch (err) {
				if (this.connected) this._fail(err?.message || t("انقطع الاتصال بالميزان."));
			} finally {
				this.reader.releaseLock();
				this.reader = null;
			}
			if (this.connected) break;
		}
	}

	_ingest(chunk) {
		this._buffer += chunk;
		let idx = this._buffer.search(/[\r\n]/);
		while (idx >= 0) {
			const line = this._buffer.slice(0, idx);
			this._buffer = this._buffer.slice(idx + 1);
			this._handleLine(line);
			idx = this._buffer.search(/[\r\n]/);
		}
		if (this._buffer.length > 128) this._buffer = this._buffer.slice(-64);
	}

	_handleLine(line) {
		const frame = parseScaleFrame(line);
		if (!frame?.stable) return;
		if (this._pendingCount > 0 && Math.abs(frame.weightKg - this._pendingKg) <= _SCALE_EPSILON_KG) {
			this._pendingCount += 1;
		} else {
			this._pendingKg = frame.weightKg;
			this._pendingCount = 1;
		}
		if (this._pendingCount >= _SCALE_STABLE_READS) {
			this.lastWeightKg = this._pendingKg;
			if (this.onStableWeight) this.onStableWeight(this.lastWeightKg);
			this._pendingCount = 0;
		}
	}

	getLastWeight() {
		return this.lastWeightKg;
	}

	_fail(message) {
		if (this.onError) this.onError(String(message || "Scale error"));
	}
}

/**
 * Wire a connect/disconnect toggle button to a PosScaleSerial instance.
 * Hidden when Web Serial is unsupported. Toggles visual "connected" state.
 */
function setupPosScaleUI({ button, scale, connectedTitle, disconnectedTitle } = {}) {
	if (!button || !scale) return null;
	if (!PosScaleSerial.isSupported()) {
		button.classList.add("d-none");
		return null;
	}
	const off = disconnectedTitle || button.title || "";
	const on = connectedTitle || off;
	const render = () => {
		button.classList.toggle("pos-scale-live", scale.connected);
		button.title = scale.connected ? on : off;
	};
	render();
	button.addEventListener("click", async () => {
		if (scale.connected) {
			await scale.disconnect();
		} else {
			await scale.connect();
		}
		render();
	});
	return scale;
}

if (typeof window !== "undefined") {
	window.PosScaleSerial = PosScaleSerial;
	window.setupPosScaleUI = setupPosScaleUI;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { parseScaleFrame, PosScaleSerial };
}
