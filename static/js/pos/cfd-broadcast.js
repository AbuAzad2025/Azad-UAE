/**
 * Customer-facing display (CFD) live-cart broadcast.
 *
 * BroadcastChannel fallback for the CFD page: when the SSE stream is offline
 * or disconnected, a CFD opened as another tab/window on the same machine
 * still receives live in-progress cart updates directly from the register.
 * The server payload contract (build_cfd_order_payload) is mirrored so the
 * CFD renders both sources identically.
 */
(() => {
	const CHANNEL = "pos-cfd";
	let bc = null;
	let sessionId = null;
	try {
		bc = typeof BroadcastChannel !== "undefined" ? new BroadcastChannel(CHANNEL) : null;
	} catch (_e) {
		bc = null;
	}

	const toNum = (v) => {
		const n = Number(v);
		return Number.isFinite(n) ? n : 0;
	};
	const round3 = (v) => Math.round(toNum(v) * 1000) / 1000;

	window.cfdBroadcast = {
		setSession(id) {
			sessionId = id || null;
		},
		/**
		 * Broadcast the live cart in the server payload shape.
		 * totals: {subtotal, tax, taxRate, discountAmount, total} (register recalc result).
		 */
		sendCart(cart, totals) {
			if (!bc || !sessionId) return;
			const t = totals || {};
			if (!Array.isArray(cart) || cart.length === 0) {
				this._post({ type: "waiting", session_id: sessionId });
				return;
			}
			let gross = 0;
			let lineDiscount = 0;
			const items = cart.map((it) => {
				const qty = toNum(it.qty);
				const price = toNum(it.price);
				const dp = toNum(it.discountPercent);
				const lineGross = qty * price;
				const lineTotal = lineGross * (1 - dp / 100);
				gross += lineGross;
				lineDiscount += lineGross - lineTotal;
				return {
					name: it.name || "—",
					quantity: qty,
					unit_price: round3(price),
					discount_percent: dp,
					discount_amount: round3(lineGross - lineTotal),
					total: round3(lineTotal),
				};
			});
			const manualDiscount = toNum(t.discountAmount);
			const tax = toNum(t.tax);
			const taxRate = toNum(t.taxRate);
			const total = toNum(t.total);
			const netBeforeManual = gross - lineDiscount;
			// taxable_amount is the net-of-discount subtotal. When taxRate === 0
			// the cart is zero-rated, so taxable = gross − line discounts −
			// header discount — derived from the lines themselves rather than
			// trusting t.subtotal, whose gross/net semantics differ between
			// register versions.
			const taxable = taxRate > 0 ? round3(total - tax) : round3(netBeforeManual - manualDiscount);
			this._post({
				type: "order_update",
				live: true,
				session_id: sessionId,
				order_number: null,
				items,
				subtotal: round3(gross),
				discount_amount: round3(lineDiscount + manualDiscount),
				promotion_discount_amount: 0,
				taxable_amount: taxable,
				tax_breakdown: {
					standard:
						taxRate > 0
							? { base: taxable, rate: taxRate, tax: round3(tax) }
							: { base: 0, rate: 0, tax: 0 },
					zero_rated: { base: taxRate > 0 ? 0 : taxable, tax: 0 },
					exempt: { base: 0, tax: 0 },
				},
				total: round3(total),
				paid_amount: 0,
				change_due: 0,
				status: "cart",
			});
		},
		/**
		 * Post a payload, surviving a crashed/closed CFD tab: BroadcastChannel
		 * throws when the receiving context is gone, and a broken broadcast
		 * must not take down the register — drop the channel instead.
		 */
		_post(payload) {
			try {
				bc.postMessage(payload);
			} catch (_e) {
				bc = null;
			}
		},
	};
})();
