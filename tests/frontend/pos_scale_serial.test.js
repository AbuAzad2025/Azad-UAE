/**
 * POS Web Serial scale driver — frame parser unit tests.
 *
 * Covers parseScaleFrame from static/js/pos/scale-serial.js across the
 * common scale protocols seen in retail hardware.
 */

const { parseScaleFrame } = require("../../static/js/pos/scale-serial");

describe("parseScaleFrame", () => {
	test("parses A&D stable header frame in kg", () => {
		const r = parseScaleFrame("ST,GS,+  1.234kg");
		expect(r).toEqual({ weightKg: 1.234, stable: true });
	});

	test("parses A&D unstable header frame as unstable", () => {
		const r = parseScaleFrame("US,GS,+  0.500kg");
		expect(r).toEqual({ weightKg: 0.5, stable: false });
	});

	test("parses overload header as unstable", () => {
		const r = parseScaleFrame("OL,GS,+  9.999kg");
		expect(r).not.toBeNull();
		expect(r.stable).toBe(false);
	});

	test("parses plain numeric line assumed kilograms", () => {
		expect(parseScaleFrame("1.234")).toEqual({ weightKg: 1.234, stable: true });
	});

	test("parses signed zero-padded plain frame", () => {
		expect(parseScaleFrame("+0001.234")).toEqual({ weightKg: 1.234, stable: true });
	});

	test("parses comma decimal separator", () => {
		expect(parseScaleFrame("0,750kg")).toEqual({ weightKg: 0.75, stable: true });
	});

	test("converts gram-denominated frame to kilograms", () => {
		expect(parseScaleFrame("500g")).toEqual({ weightKg: 0.5, stable: true });
	});

	test("does not treat kg suffix as grams", () => {
		expect(parseScaleFrame("2.500kg")).toEqual({ weightKg: 2.5, stable: true });
	});

	test("rejects negative weight", () => {
		expect(parseScaleFrame("-1.234kg")).toBeNull();
	});

	test("rejects frame without any number", () => {
		expect(parseScaleFrame("ST,GS,kg")).toBeNull();
	});

	test("rejects empty and blank input", () => {
		expect(parseScaleFrame("")).toBeNull();
		expect(parseScaleFrame("   ")).toBeNull();
		expect(parseScaleFrame(null)).toBeNull();
		expect(parseScaleFrame(undefined)).toBeNull();
	});

	test("rounds to gram precision", () => {
		const r = parseScaleFrame("1.23456kg");
		expect(r.weightKg).toBe(1.235);
	});
});
