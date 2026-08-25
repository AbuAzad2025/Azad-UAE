import { csrf, fmt, qs, qsa, toNum } from "./core.js";
import { showAlert } from "./ui.js";

let pinResolver = null;
const settlePin = (token) => {
	if (pinResolver) {
		pinResolver(token);
		pinResolver = null;
	}
};
const requestOverrideToken = (action) =>
	new Promise((resolve) => {
		const modalEl = qs("#posPinModal");
		if (!modalEl) {
			resolve(null);
			return;
		}
		pinResolver = resolve;
		modalEl.dataset.action = action;
		qs("#posPinInput").value = "";
		qs("#posPinError").classList.add("d-none");
		window.$("#posPinModal").modal("show");
		setTimeout(() => qs("#posPinInput").focus(), 300);
	});
const confirmPin = async () => {
	const err = qs("#posPinError");
	const action = qs("#posPinModal").dataset.action || "";
	const pin = qs("#posPinInput").value.trim();
	try {
		const r = await fetch("/pos/api/authorize-override", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-CSRFToken": csrf,
			},
			credentials: "same-origin",
			body: JSON.stringify({ pin, action }),
		});
		const j = await r.json().catch(() => ({}));
		if (r.ok && j.success && (j.data?.override_token || j.override_token)) {
			window.$("#posPinModal").modal("hide");
			settlePin(j.data?.override_token || j.override_token);
			return;
		}
		err.textContent =
			j.message || j.error || "\u062a\u0639\u0630\u0631 \u0627\u0644\u062a\u0641\u0648\u064a\u0636";
		err.classList.remove("d-none");
	} catch (_) {
		err.textContent =
			"\u0641\u0634\u0644 \u0627\u0644\u0627\u062a\u0635\u0627\u0644 \u0628\u0627\u0644\u062e\u0627\u062f\u0645";
		err.classList.remove("d-none");
	}
};
const postWithOverride = async (url, body, action) => {
	const send = async (token) => {
		const payload = token ? { ...body, override_token: token } : body;
		const r = await fetch(url, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				Accept: "application/json",
				"X-CSRFToken": csrf,
			},
			credentials: "same-origin",
			body: JSON.stringify(payload),
		});
		const j = await r.json().catch(() => ({}));
		return { r, j };
	};
	const first = await send(null);
	if (first.r.status !== 403) return first;
	const token = await requestOverrideToken(action);
	if (!token) return first;
	return send(token);
};
const needsOverride = (r, j) =>
	r.status === 403 &&
	typeof (j.message || j.error) === "string" &&
	(j.message || j.error).includes("\u062a\u0641\u0648\u064a\u0636");

const SPLIT_METHODS = [
	["cash", "\u0646\u0642\u062f\u064a"],
	["card", "\u0628\u0637\u0627\u0642\u0629"],
	["bank_transfer", "\u062a\u062d\u0648\u064a\u0644 \u0628\u0646\u0643\u064a"],
	[
		"e_wallet",
		"\u0645\u062d\u0641\u0638\u0629 \u0625\u0644\u0643\u062a\u0631\u0648\u0646\u064a\u0629",
	],
	["cheque", "\u0634\u064a\u0643"],
];
const splitEnabled = () => qs("#splitTenderToggle")?.checked === true;
const splitSumRefresh = () => {
	let sum = 0;
	qsa("#splitTenderRows .split-amount").forEach((inp) => {
		sum += toNum(inp.value) || 0;
	});
	const el = qs("#splitTenderSum");
	if (el) el.textContent = fmt(sum);
};
const addSplitRow = (amount, method) => {
	const rows = qs("#splitTenderRows");
	if (!rows) return;
	const row = document.createElement("div");
	row.className = "split-row d-flex align-items-center mb-1";
	const amountInp = document.createElement("input");
	amountInp.type = "number";
	amountInp.step = "0.01";
	amountInp.min = "0";
	amountInp.className = "form-control form-control-sm split-amount mr-1";
	amountInp.value = amount || "";
	const methodSel = document.createElement("select");
	methodSel.className = "form-control form-control-sm split-method mr-1";
	SPLIT_METHODS.forEach(([val, label]) => {
		const opt = document.createElement("option");
		opt.value = val;
		opt.textContent = label;
		methodSel.appendChild(opt);
	});
	methodSel.value = method || "cash";
	const removeBtn = document.createElement("button");
	removeBtn.type = "button";
	removeBtn.className = "btn btn-sm btn-outline-danger split-remove";
	removeBtn.textContent = "\u00d7";
	removeBtn.addEventListener("click", () => {
		row.remove();
		splitSumRefresh();
	});
	amountInp.addEventListener("input", splitSumRefresh);
	row.appendChild(amountInp);
	row.appendChild(methodSel);
	row.appendChild(removeBtn);
	rows.appendChild(row);
	splitSumRefresh();
};
const readSplitPayments = () => {
	const rows = qsa("#splitTenderRows .split-row");
	if (!rows.length) {
		showAlert(
			"\u0623\u0636\u0641 \u062f\u0641\u0639\u0629 \u0648\u0627\u062d\u062f\u0629 \u0639\u0644\u0649 \u0627\u0644\u0623\u0642\u0644 \u0623\u0648 \u0623\u0648\u0642\u0641 \u0627\u0644\u062f\u0641\u0639 \u0627\u0644\u0645\u062a\u0639\u062f\u062f",
			"warning",
		);
		return null;
	}
	const cur = qs("#currency").value;
	const rate = toNum(qs("#exchangeRate").value) || 1;
	const chunks = [];
	for (const row of rows) {
		const amount = toNum(row.querySelector(".split-amount")?.value) || 0;
		const method = row.querySelector(".split-method")?.value || "";
		if (amount <= 0 || !method) {
			showAlert(
				"\u0643\u0644 \u062f\u0641\u0639\u0629 \u062a\u062d\u062a\u0627\u062c \u0645\u0628\u0644\u063a\u064b\u0627 \u0623\u0643\u0628\u0631 \u0645\u0646 \u0635\u0641\u0631 \u0648\u0637\u0631\u064a\u0642\u0629 \u062f\u0641\u0639",
				"warning",
			);
			return null;
		}
		chunks.push({ amount, payment_method: method, currency: cur, exchange_rate: rate });
	}
	return chunks;
};
const syncPay = () => {
	const paySel = qs("#paymentMethod");
	const refField = qs("#refField");
	const v = paySel ? paySel.value : "";
	qsa("#posPayMethod .pm").forEach((pm) => {
		pm.classList.toggle("active", pm.getAttribute("data-method") === v);
	});
	if (refField) refField.classList.toggle("show", !!v);
};

export {
	addSplitRow,
	confirmPin,
	needsOverride,
	postWithOverride,
	readSplitPayments,
	requestOverrideToken,
	SPLIT_METHODS,
	settlePin,
	splitEnabled,
	splitSumRefresh,
	syncPay,
};
