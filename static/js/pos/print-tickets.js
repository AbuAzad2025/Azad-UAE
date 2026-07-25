/**
 * Split-print ticket delivery after checkout.
 *
 * Fetches per-printer ticket payloads from the server and delivers each to
 * its target: agent_* printers via the localhost hardware agent, and
 * webusb/webserial printers directly through EscposPrinter. Individual
 * ticket failures are collected, never thrown — printing must never block
 * or break the checkout UX (the standard browser print remains available).
 */
/* global EscposPrinter, buildReceiptBytes */

const _AGENT_URL = "http://127.0.0.1:8567";
let _escposSingleton = null;

async function _deliverAgentTicket(ticket) {
	const res = await fetch(`${_AGENT_URL}/print-receipt`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ printer: ticket.printer, content: ticket.content }),
	});
	if (!res.ok) throw new Error(`agent ${res.status}`);
}

async function _deliverBrowserTicket(ticket) {
	if (!window.EscposPrinter || !window.buildReceiptBytes) {
		throw new Error("escpos module unavailable");
	}
	if (!_escposSingleton) _escposSingleton = new EscposPrinter();
	if (!_escposSingleton.channel) {
		if (ticket.connection_type === "webusb") await _escposSingleton.connectWebUsb();
		else await _escposSingleton.connectSerial();
	}
	await _escposSingleton.print(buildReceiptBytes(ticket.content));
}

/**
 * Print all split tickets for a sale. Resolves with
 * ``{ printed: number, failed: string[] }`` — never rejects.
 */
async function printSaleTickets(saleId) {
	const summary = { printed: 0, failed: [] };
	let data;
	try {
		const res = await fetch(`/pos/api/sale/${saleId}/print-tickets`, {
			credentials: "same-origin",
		});
		data = await res.json();
	} catch {
		summary.failed.push("fetch");
		return summary;
	}
	const tickets = data?.success ? data.tickets || [] : [];
	for (const ticket of tickets) {
		try {
			if (ticket.connection_type === "webusb" || ticket.connection_type === "webserial") {
				await _deliverBrowserTicket(ticket);
			} else {
				await _deliverAgentTicket(ticket);
			}
			summary.printed += 1;
		} catch {
			summary.failed.push(ticket.printer_name || ticket.role || "unknown");
		}
	}
	return summary;
}

/**
 * Best-effort local receipt for a sale that was queued offline by the
 * service worker. Builds the ESC/POS content from the live cart and posts
 * it straight to the hardware agent's default printer. Never throws.
 */
async function printQueuedCartReceipt(cart, totals, payload = {}) {
	try {
		const lines = [
			{ text: payload.sale_reference || "OFFLINE", align: "center", bold: true, double: true },
			{ separator: true },
		];
		for (const it of cart || []) {
			lines.push({ text: `${it.qty} x ${it.name}`, align: "left" });
			lines.push({ text: `   ${Number(it.price * it.qty).toFixed(3)}`, align: "right" });
		}
		lines.push({ separator: true });
		if (totals?.total != null) {
			lines.push({ text: `TOTAL ${Number(totals.total).toFixed(3)}`, align: "center", bold: true });
		}
		const res = await fetch(`${_AGENT_URL}/print-receipt`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ content: { lines, cut: true, open_drawer: true } }),
		});
		return res.ok;
	} catch {
		return false;
	}
}

window.printSaleTickets = printSaleTickets;
window.printQueuedCartReceipt = printQueuedCartReceipt;
