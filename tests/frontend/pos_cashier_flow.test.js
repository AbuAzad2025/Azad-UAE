/**
 * POS Cashier Flow — Unit Tests (Jest)
 *
 * Tests pure cart/pricing logic from static/js/pos/cashier-logic.js
 * (aligned with static/js/pos/index.js quick-total estimate).
 */

const { createCashierLogic } = require("../../static/js/pos/cashier-logic");

describe("POS Cashier Flow", () => {
	const apple = {
		id: 1,
		name: "Apple",
		price: 5.0,
		sku: "APL001",
		barcode: "123456",
	};
	const banana = {
		id: 2,
		name: "Banana",
		price: 3.0,
		sku: "BAN001",
		barcode: "789012",
	};
	let POS;

	beforeEach(() => {
		POS = createCashierLogic("AED");
	});

	describe("Cart Operations", () => {
		test("addToCart adds new product", () => {
			const r = POS.addToCart(apple);
			expect(r).toEqual({ action: "added", qty: 1 });
			expect(POS.state.cart).toHaveLength(1);
			expect(POS.state.cart[0].name).toBe("Apple");
			expect(POS.state.cart[0].qty).toBe(1);
		});

		test("addToCart increments quantity for duplicate", () => {
			POS.addToCart(apple);
			const r = POS.addToCart(apple);
			expect(r).toEqual({ action: "incremented", qty: 2 });
			expect(POS.state.cart).toHaveLength(1);
			expect(POS.state.cart[0].qty).toBe(2);
		});

		test("addToCart handles multiple distinct products", () => {
			POS.addToCart(apple);
			POS.addToCart(banana);
			expect(POS.state.cart).toHaveLength(2);
		});

		test("updateQty modifies quantity", () => {
			POS.addToCart(apple);
			expect(POS.updateQty(1, 5)).toBe(true);
			expect(POS.state.cart[0].qty).toBe(5);
		});

		test("updateQty clamps to minimum 0.001", () => {
			POS.addToCart(apple);
			POS.updateQty(1, -10);
			expect(POS.state.cart[0].qty).toBe(0.001);
		});

		test("removeFromCart removes product", () => {
			POS.addToCart(apple);
			POS.addToCart(banana);
			expect(POS.removeFromCart(1)).toBe(true);
			expect(POS.state.cart).toHaveLength(1);
			expect(POS.state.cart[0].id).toBe(2);
		});

		test("removeFromCart returns false for missing product", () => {
			expect(POS.removeFromCart(999)).toBe(false);
		});

		test("clearCart empties cart and customer", () => {
			POS.addToCart(apple);
			POS.state.customer = { id: 1, name: "Test" };
			POS.clearCart();
			expect(POS.isCartEmpty()).toBe(true);
			expect(POS.state.customer).toBeNull();
		});
	});

	describe("Pricing & Recalc", () => {
		test("recalc returns zero for empty cart", () => {
			const r = POS.recalc(0, 0, 0, false);
			expect(r.subtotal).toBe("0.00");
			expect(r.total).toBe("0.00");
		});

		test("recalc computes correct subtotal and total", () => {
			POS.addToCart(apple);
			POS.addToCart(banana);
			const r = POS.recalc(0, 0, 0, false);
			expect(r.subtotal).toBe("8.00");
			expect(r.total).toBe("8.00");
		});

		test("recalc applies tax when prices exclude VAT", () => {
			POS.addToCart(apple);
			const r = POS.recalc(10, 0, 0, false);
			expect(r.subtotal).toBe("5.00");
			expect(r.tax).toBe("0.50");
			expect(r.total).toBe("5.50");
		});

		test("recalc skips tax when prices include VAT", () => {
			POS.addToCart(apple);
			const r = POS.recalc(10, 0, 0, true);
			expect(r.tax).toBe("0.00");
			expect(r.total).toBe("5.00");
		});

		test("recalc applies shipping", () => {
			POS.addToCart(apple);
			const r = POS.recalc(0, 0, 10, false);
			expect(r.total).toBe("15.00");
		});

		test("recalc clamps total to minimum 0", () => {
			POS.addToCart(apple);
			const r = POS.recalc(0, 100, 0, false);
			expect(r.total).toBe("0.00");
		});

		test("priceForCurrency converts foreign currency", () => {
			expect(POS.priceForCurrency(100, "USD", 3.67)).toBeCloseTo(27.25, 2);
			expect(POS.priceForCurrency(100, "AED", 1)).toBe(100);
		});
	});

	describe("Discount Application", () => {
		test("updateDiscount applies valid percentage", () => {
			POS.addToCart(apple);
			expect(POS.updateDiscount(1, 20)).toBe(true);
			expect(POS.state.cart[0].discountPercent).toBe(20);
		});

		test("updateDiscount clamps above 100", () => {
			POS.addToCart(apple);
			POS.updateDiscount(1, 150);
			expect(POS.state.cart[0].discountPercent).toBe(100);
		});

		test("updateDiscount clamps below 0", () => {
			POS.addToCart(apple);
			POS.updateDiscount(1, -10);
			expect(POS.state.cart[0].discountPercent).toBe(0);
		});

		test("recalc with line discount", () => {
			POS.addToCart(apple);
			POS.updateDiscount(1, 20);
			const r = POS.recalc(0, 0, 0, false);
			expect(r.subtotal).toBe("4.00");
			expect(r.discount).toBe("1.00");
		});
	});

	describe("Full Cashier Interaction Flow", () => {
		test("complete flow: add → mutate → discount → checkout → clear", () => {
			POS.addToCart(apple);
			POS.addToCart(banana);
			POS.addToCart({ id: 3, name: "Milk", price: 2.5, sku: "MLK001" });
			expect(POS.state.cart).toHaveLength(3);

			POS.updateQty(1, 3);
			POS.updateQty(2, 2);
			expect(POS.state.cart[0].qty).toBe(3);
			expect(POS.state.cart[1].qty).toBe(2);

			POS.updateDiscount(1, 10);

			const totals = POS.recalc(5, 2.0, 3.0, false);
			expect(totals.subtotal).toBe("22.00");
			expect(totals.discount).toBe("3.50");
			expect(totals.tax).toBe("1.10");
			expect(totals.total).toBe("24.10");

			expect(POS.isCartEmpty()).toBe(false);

			POS.clearCart();
			expect(POS.isCartEmpty()).toBe(true);
			expect(POS.state.customer).toBeNull();
		});
	});
});
