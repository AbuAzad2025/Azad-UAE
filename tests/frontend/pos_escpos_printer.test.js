/**
 * Browser ESC/POS builder tests — static/js/pos/escpos-printer.js
 * Mirrors the Python agent builder semantics byte-for-byte where shared.
 */

const { buildReceiptBytes } = require("../../static/js/pos/escpos-printer");

describe("buildReceiptBytes", () => {
	test("starts with init command", () => {
		const out = buildReceiptBytes({ lines: [] });
		expect([...out.slice(0, 2)]).toEqual([0x1b, 0x40]);
	});

	test("centered bold line has alignment and emphasis bytes", () => {
		const out = buildReceiptBytes({ lines: [{ text: "Hi", align: "center", bold: true }] });
		const arr = [...out];
		expect(arr).toContain(0x1b);
		// ESC a 01 center
		expect(arr.join(",")).toContain([0x1b, 0x61, 0x01].join(","));
		// ESC E 01 bold on
		expect(arr.join(",")).toContain([0x1b, 0x45, 0x01].join(","));
	});

	test("double size emits GS ! 0x11", () => {
		const out = buildReceiptBytes({ lines: [{ text: "Big", double: true }] });
		expect([...out].join(",")).toContain([0x1d, 0x21, 0x11].join(","));
	});

	test("separator line renders dashes", () => {
		const out = buildReceiptBytes({ lines: [{ separator: true }] });
		const text = new TextDecoder().decode(out);
		expect(text).toContain("-".repeat(32));
	});

	test("string line shorthand works", () => {
		const out = buildReceiptBytes({ lines: ["plain"] });
		expect(new TextDecoder().decode(out)).toContain("plain\n");
	});

	test("drawer pulse included before cut when requested", () => {
		const out = [...buildReceiptBytes({ lines: [], open_drawer: true })];
		const joined = out.join(",");
		const pulse = [0x1b, 0x70, 0x00, 0x19, 0xfa].join(",");
		const cut = [0x1d, 0x56, 0x00].join(",");
		expect(joined).toContain(pulse);
		expect(joined.indexOf(pulse)).toBeLessThan(joined.indexOf(cut));
	});

	test("cut can be disabled", () => {
		const out = [...buildReceiptBytes({ lines: [], cut: false })];
		expect(out.join(",")).not.toContain([0x1d, 0x56, 0x00].join(","));
	});

	test("feed is capped at ten newlines", () => {
		const out = [...buildReceiptBytes({ lines: [], feed: 99, cut: false })];
		const newlines = out.filter((b) => b === 0x0a).length;
		expect(newlines).toBeLessThanOrEqual(10);
	});

	test("utf-8 text survives encoding", () => {
		const out = buildReceiptBytes({ lines: [{ text: "فاتورة" }] });
		expect(new TextDecoder().decode(out)).toContain("فاتورة");
	});
});
