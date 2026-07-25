/**
 * Offline catalog scale-barcode parser tests —
 * static/js/pos/offline-catalog.js parseScaleBarcodeLocal mirrors
 * utils/pos_helpers.parse_scale_barcode exactly.
 */

const { parseScaleBarcodeLocal } = require("../../static/js/pos/offline-catalog");

/**
 * Build a valid prefix-20 scale EAN-13 for an item code + gram weight.
 */
function makeScaleCode(itemCode, grams) {
	const body = `20${String(itemCode).padStart(5, "0")}${String(grams).padStart(5, "0")}`;
	const digits = body.split("").map(Number);
	const checksum = (10 - ((digits.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0) + 3 * digits.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0)) % 10)) % 10;
	return `${body}${checksum}`;
}

describe("parseScaleBarcodeLocal", () => {
	test("parses a valid scale barcode into item code + kg", () => {
		const code = makeScaleCode(12345, 1500);
		expect(parseScaleBarcodeLocal(code)).toEqual({ itemCode: "12345", weightKg: 1.5 });
	});

	test("parses gram-level precision", () => {
		const code = makeScaleCode(99, 250);
		expect(parseScaleBarcodeLocal(code)).toEqual({ itemCode: "00099", weightKg: 0.25 });
	});

	test("rejects bad checksum", () => {
		const code = makeScaleCode(12345, 1500);
		const tampered = `${code.slice(0, 12)}${(Number(code[12]) + 1) % 10}`;
		expect(parseScaleBarcodeLocal(tampered)).toBeNull();
	});

	test("rejects wrong prefix", () => {
		const code = `30${makeScaleCode(12345, 1500).slice(2)}`;
		expect(parseScaleBarcodeLocal(code)).toBeNull();
	});

	test("rejects non-13 length and non-digits", () => {
		expect(parseScaleBarcodeLocal("2012345")).toBeNull();
		expect(parseScaleBarcodeLocal("20123456789A5")).toBeNull();
	});

	test("rejects empty input", () => {
		expect(parseScaleBarcodeLocal("")).toBeNull();
		expect(parseScaleBarcodeLocal(null)).toBeNull();
		expect(parseScaleBarcodeLocal(undefined)).toBeNull();
	});

	test("matches server parser on a known vector", () => {
		// cross-checked against utils/pos_helpers.parse_scale_barcode
		const code = makeScaleCode(77777, 12345);
		const r = parseScaleBarcodeLocal(code);
		expect(r.itemCode).toBe("77777");
		expect(r.weightKg).toBe(12.345);
	});
});
