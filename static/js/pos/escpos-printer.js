/**
 * Browser-side ESC/POS receipt builder + direct printer delivery.
 *
 * Pure byte builder (testable in Node) plus WebUSB/WebSerial glue for
 * agent-less printing. The localhost hardware agent remains the primary
 * path (code pages, serial, drawers); this module covers modern browsers
 * with USB/serial printers that accept UTF-8.
 */
/* global module, navigator, TextEncoder, Uint8Array */

const ESC = 0x1b;
const GS = 0x1d;
const CMD_INIT = [ESC, 0x40];
const CMD_CUT_FULL = [GS, 0x56, 0x00];
const CMD_DRAWER_PIN2 = [ESC, 0x70, 0x00, 0x19, 0xfa];
const _ALIGN = { left: 0, center: 1, right: 2 };
const _USB_TRANSFER_TIMEOUT_MS = 10000;

/**
 * Reject a slow hardware operation after a hard ceiling instead of letting
 * a wedged USB endpoint hang the print forever.
 */
function _withTimeout(promise, ms, message) {
	return new Promise((resolve, reject) => {
		const timer = setTimeout(() => reject(new Error(message)), ms);
		promise.then(
			(value) => {
				clearTimeout(timer);
				resolve(value);
			},
			(error) => {
				clearTimeout(timer);
				reject(error);
			},
		);
	});
}

function _lineBytes(text, { align = "left", bold = false, double = false } = {}) {
	const bytes = [];
	bytes.push(ESC, 0x61, _ALIGN[align] ?? 0);
	bytes.push(ESC, 0x45, bold ? 1 : 0);
	bytes.push(GS, 0x21, double ? 0x11 : 0x00);
	for (const b of new TextEncoder().encode(String(text))) bytes.push(b);
	bytes.push(0x0a);
	bytes.push(ESC, 0x45, 0, GS, 0x21, 0x00, ESC, 0x61, 0);
	return bytes;
}

/**
 * Build a full receipt as a Uint8Array: init, lines, optional drawer pulse,
 * optional cut. Mirrors scripts/hardware_agent/pos_hardware_agent.py.
 */
function buildReceiptBytes(content = {}) {
	const bytes = [...CMD_INIT];
	for (const raw of content.lines || []) {
		const line = typeof raw === "string" ? { text: raw } : raw;
		if (line.separator) {
			bytes.push(..._lineBytes("-".repeat(Number(line.width) || 32)));
			continue;
		}
		bytes.push(
			..._lineBytes(line.text ?? "", {
				align: line.align,
				bold: !!line.bold,
				double: !!line.double,
			}),
		);
	}
	const feed = Math.min(Number(content.feed) || 0, 10);
	for (let i = 0; i < feed; i++) bytes.push(0x0a);
	if (content.open_drawer) bytes.push(...CMD_DRAWER_PIN2);
	if (content.cut !== false) bytes.push(0x0a, 0x0a, ...CMD_CUT_FULL);
	return new Uint8Array(bytes);
}

class EscposPrinter {
	constructor() {
		this.device = null;
		this.port = null;
		this.channel = null;
	}

	static webUsbSupported() {
		return typeof navigator !== "undefined" && !!navigator.usb;
	}

	static webSerialSupported() {
		return typeof navigator !== "undefined" && !!navigator.serial;
	}

	async connectWebUsb() {
		if (!EscposPrinter.webUsbSupported()) throw new Error("WebUSB غير مدعوم في هذا المتصفح.");
		// Optional tenant-scoped device filter (vendor/product IDs) set via
		// window._PRINTER_USB_FILTERS; an absent/empty config keeps the old
		// "show every device" behaviour.
		const filters = Array.isArray(window._PRINTER_USB_FILTERS) ? window._PRINTER_USB_FILTERS : [];
		this.device = await navigator.usb.requestDevice({ filters });
		await this.device.open();
		if (this.device.configuration === null) await this.device.selectConfiguration(1);
		await this.device.claimInterface(0);
		this.channel = "webusb";
		return true;
	}

	async connectSerial({ baudRate = 9600 } = {}) {
		if (!EscposPrinter.webSerialSupported())
			throw new Error("Web Serial غير مدعوم في هذا المتصفح.");
		this.port = await navigator.serial.requestPort();
		await this.port.open({ baudRate });
		this.channel = "webserial";
		return true;
	}

	async print(bytes) {
		if (this.channel === "webusb" && this.device) {
			const endpoint = this.device.configuration.interfaces[0].alternate.endpoints.find(
				(e) => e.direction === "out",
			);
			if (!endpoint) throw new Error("لم يعثر على نقطة إخراج USB للطابعة.");
			await _withTimeout(
				this.device.transferOut(endpoint.endpointNumber, bytes),
				_USB_TRANSFER_TIMEOUT_MS,
				"تجاوزت مهلة الطباعة عبر USB.",
			);
			return true;
		}
		if (this.channel === "webserial" && this.port?.writable) {
			const writer = this.port.writable.getWriter();
			try {
				await writer.write(bytes);
			} finally {
				writer.releaseLock();
			}
			return true;
		}
		throw new Error("الطابعة غير متصلة.");
	}

	async disconnect() {
		try {
			if (this.device) await this.device.close();
			if (this.port) await this.port.close();
		} finally {
			this.device = null;
			this.port = null;
			this.channel = null;
		}
	}
}

if (typeof window !== "undefined") {
	window.EscposPrinter = EscposPrinter;
	window.buildReceiptBytes = buildReceiptBytes;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { buildReceiptBytes, EscposPrinter };
}
