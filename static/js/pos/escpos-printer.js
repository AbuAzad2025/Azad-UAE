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

function _encodeCp864(text) {
	// Map common Arabic characters to CP864 (Arabic DOS encoding)
	// This is a simplified mapping - in production, use a full CP864 table
	const cp864Map = {
		'ا': 0xC7, 'ب': 0xD6, 'ت': 0xD8, 'ث': 0xD9, 'ج': 0xDA, 'ح': 0xDC,
		'خ': 0xDD, 'د': 0xDE, 'ذ': 0xDF, 'ر': 0xE0, 'ز': 0xE1,
		'س': 0xE3, 'ش': 0xE4, 'ص': 0xE5, 'ض': 0xE6, 'ط': 0xE7,
		'ظ': 0xE8, 'ع': 0xE9, 'غ': 0xEA, 'ف': 0xEB, 'ق': 0xEC,
		'ك': 0xED, 'ل': 0xEE, 'م': 0xEF, 'ن': 0xF0, 'ه': 0xF1,
		'و': 0xF2, 'ي': 0xF3, 'ة': 0xF4, 'ى': 0xF5, 'أ': 0xC5,
		'إ': 0xC6, 'ؤ': 0xC8, 'ئ': 0xC9, 'ء': 0xCA, 'آ': 0xCB,
		'٠': 0xA0, '١': 0xA1, '٢': 0xA2, '٣': 0xA3, '٤': 0xA4,
		'٥': 0xA5, '٦': 0xA6, '٧': 0xA7, '٨': 0xA8, '٩': 0xA9,
		'٠': 0xA0, '،': 0xAC, '؛': 0xBB, '؟': 0xBF, '٪': 0x25,
		'٫': 0xB0, '٪': 0x25, '٪': 0x25,
		' ': 0x20, '.': 0x2E, ':': 0x3A, '-': 0x2D,
		'(': 0x28, ')': 0x29, '+': 0x2B, '/': 0x2F,
		'0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
		'5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
	};
	const bytes = [];
	for (const ch of String(text)) {
		if (cp864Map[ch] !== undefined) {
			bytes.push(cp864Map[ch]);
		} else if (ch.charCodeAt(0) < 128) {
			// ASCII characters
			bytes.push(ch.charCodeAt(0));
		} else {
			// Fallback for unmapped Arabic - use UTF-8 bytes as fallback
			for (const b of new TextEncoder().encode(ch)) bytes.push(b);
		}
	}
	bytes.push(0x0a); // LF
	return bytes;
}

function _lineBytes(text, { align = "left", bold = false, double = false } = {}) {
	const bytes = [];
	bytes.push(ESC, 0x61, _ALIGN[align] ?? 0);
	bytes.push(ESC, 0x45, bold ? 1 : 0);
	bytes.push(GS, 0x21, double ? 0x11 : 0x00);
	bytes.push(..._encodeCp864(text));
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
		if (!EscposPrinter.webUsbSupported()) throw new Error(t("WebUSB غير مدعوم في هذا المتصفح."));
		// Optional tenant-scoped device filter (vendor/product IDs) set via
		// window._PRINTER_USB_FILTERS; an absent/empty config keeps the old
		// "show every device" behavior.
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
			throw new Error(t("Web Serial غير مدعوم في هذا المتصفح."));
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
			if (!endpoint) throw new Error(t("لم يعثر على نقطة إخراج USB للطابعة."));
			await _withTimeout(
				this.device.transferOut(endpoint.endpointNumber, bytes),
				_USB_TRANSFER_TIMEOUT_MS,
				t("تجاوزت مهلة الطباعة عبر USB."),
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
		throw new Error(t("الطابعة غير متصلة."));
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
