/**
 * Pure POS cashier logic (cart + quick totals).
 * Mirrors static/js/pos/index.js — testable without DOM.
 */
/* global module */

function toNum(v) {
	const n = Number(v);
	return Number.isFinite(n) ? n : 0;
}

function fmt(n) {
	return toNum(n).toFixed(2);
}

function esc(s) {
	if (s == null) return "";
	return String(s)
		.replace(/&/g, "&amp;")
		.replace(/</g, "&lt;")
		.replace(/>/g, "&gt;")
		.replace(/"/g, "&quot;");
}

function priceForCurrency(basePrice, currency, baseCurrency, rate) {
	if (currency !== baseCurrency && toNum(rate) > 0) {
		return toNum(basePrice) / toNum(rate);
	}
	return toNum(basePrice);
}

function createCashierLogic(baseCurrency = "AED") {
	const state = { customer: null, cart: [] };

	return {
		baseCurrency,
		state,
		toNum,
		fmt,
		esc,
		priceForCurrency(basePrice, currency, rate) {
			return priceForCurrency(basePrice, currency, baseCurrency, rate);
		},
		addToCart(product) {
			const existing = state.cart.find((x) => x.id === product.id);
			if (existing) {
				existing.qty = toNum(existing.qty) + 1;
				return { action: "incremented", qty: existing.qty };
			}
			state.cart.push({
				id: product.id,
				name: product.name,
				sku: product.sku || "",
				barcode: product.barcode || "",
				qty: 1,
				basePrice: toNum(product.price),
				price: priceForCurrency(toNum(product.price), baseCurrency, baseCurrency, 1),
				discountPercent: toNum(product.discountPercent),
			});
			return { action: "added", qty: 1 };
		},
		updateQty(productId, newQty) {
			const item = state.cart.find((x) => x.id === productId);
			if (!item) return false;
			item.qty = Math.max(0.001, toNum(newQty));
			return true;
		},
		updateDiscount(productId, discountPct) {
			const item = state.cart.find((x) => x.id === productId);
			if (!item) return false;
			item.discountPercent = Math.max(0, Math.min(100, toNum(discountPct)));
			return true;
		},
		removeFromCart(productId) {
			const idx = state.cart.findIndex((x) => x.id === productId);
			if (idx === -1) return false;
			state.cart.splice(idx, 1);
			return true;
		},
		recalc(taxRate, discountAmount, shipping, pricesIncludeVat) {
			let subtotal = 0;
			let discount = 0;
			state.cart.forEach((it) => {
				const lineBase = it.qty * it.price;
				const lineDisc = lineBase * (it.discountPercent / 100);
				subtotal += lineBase - lineDisc;
				discount += lineDisc;
			});
			const quickTax = pricesIncludeVat ? 0 : subtotal * (toNum(taxRate) / 100);
			const quickTotal = Math.max(0, subtotal + quickTax + toNum(shipping) - toNum(discountAmount));
			return {
				subtotal: fmt(subtotal),
				discount: fmt(discount + toNum(discountAmount)),
				tax: fmt(quickTax),
				total: fmt(quickTotal),
			};
		},
		clearCart() {
			state.cart = [];
			state.customer = null;
		},
		isCartEmpty() {
			return state.cart.length === 0;
		},
	};
}

module.exports = {
	toNum,
	fmt,
	esc,
	priceForCurrency,
	createCashierLogic,
};
