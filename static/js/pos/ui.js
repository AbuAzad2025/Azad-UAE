import { addToCart } from "./cart.js";
import {
	currencySymbolFor,
	esc,
	fetchJson,
	fmt,
	priceForCurrency,
	qs,
	selectedCurrency,
	state,
	t,
	warehouseParam,
} from "./core.js";

const _customerTimer = null;
const _productTimer = null;
let productBusy = false;

const showAlert = (msg, level = "danger") => {
	const el = qs("#posAlert");
	el.className = `alert alert-${level}`;
	el.textContent = msg;
	el.classList.remove("d-none");
	setTimeout(() => {
		el.classList.add("d-none");
	}, 5000);
};
const showModalAlert = (modalId, msg, level = "danger") => {
	const el = qs(`#${modalId}Alert`);
	if (!el) {
		showAlert(msg, level);
		return;
	}
	el.className = `alert alert-${level} mb-3`;
	el.textContent = msg;
	el.classList.remove("d-none");
	setTimeout(() => {
		el.classList.add("d-none");
	}, 6000);
};
const hideModalAlert = (modalId) => {
	const el = qs(`#${modalId}Alert`);
	if (el) el.classList.add("d-none");
};
const customerHint = () => {
	const el = qs("#customerSelectedHint");
	if (state.customer) {
		el.textContent = `${t("العميل المختار")} ${state.customer.text}`;
		el.className = "text-success mt-2";
	} else {
		el.textContent = "لم يتم اختيار عميل بعد";
		el.className = "text-muted mt-2";
	}
};
const loadOrderTypes = async () => {
	const sel = qs("#orderType");
	if (!sel) return;
	try {
		const r = await fetch("/pos/api/order-types", {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		});
		const data = await r.json();
		if (!data.success) return;
		sel.innerHTML = "";
		(data.order_types || []).forEach((ot) => {
			const o = document.createElement("option");
			o.value = ot.code;
			o.textContent = ot.display_name;
			sel.appendChild(o);
		});
		if (data.default_code) sel.value = data.default_code;
		toggleTableField();
	} catch (_) {}
};
const toggleTableField = () => {
	const tableField = qs("#tableField");
	const sel = qs("#orderType");
	if (!tableField || !sel) return;
	const code = (sel.value || "").toLowerCase();
	const needsTable = code.includes("dine") || code.includes("table");
	tableField.classList.toggle("d-none", !needsTable);
	if (needsTable) loadTableOptions();
};
const loadTableOptions = async () => {
	const sel = qs("#tableSelect");
	if (!sel || sel.dataset.loaded) return;
	try {
		const r = await fetch("/pos/api/tables", {
			credentials: "same-origin",
			headers: { Accept: "application/json" },
		});
		const tables = await r.json();
		(tables || []).forEach((tbl) => {
			const o = document.createElement("option");
			o.value = tbl.id;
			o.textContent = tbl.floor_name ? `${tbl.label} — ${tbl.floor_name}` : tbl.label;
			sel.appendChild(o);
		});
		sel.dataset.loaded = "1";
	} catch (_) {}
};
const renderProductResults = (res) => {
	state.lastProductResults = res || [];
	const box = qs("#productResults");
	box.innerHTML = "";
	(res || []).forEach((p) => {
		const a = document.createElement("button");
		a.type = "button";
		const stockBadge = p.is_out_of_stock
			? '<span class="badge badge-warning badge-pill ml-1">نفد</span>'
			: `<span class="badge badge-secondary badge-pill ml-1">${fmt(p.stock)}</span>`;
		a.className =
			"list-group-item list-group-item-action d-flex justify-content-between align-items-center";
		a.innerHTML = `<span>${esc(p.text)}${p.is_inactive ? ` <small class="text-danger">(${t("غير نشط")})</small>` : ""}</span><span>${stockBadge} <span class="badge badge-primary badge-pill">${fmt(priceForCurrency(p.price))} ${currencySymbolFor(selectedCurrency())}</span></span>`;
		a.addEventListener("click", async () => {
			if (p.is_inactive) {
				showAlert("المنتج غير نشط.", "warning");
				return;
			}
			await addToCart(p);
			qs("#productSearch").value = "";
			box.classList.add("d-none");
			qs("#productSearch").focus();
		});
		box.appendChild(a);
	});
	box.classList.toggle("d-none", !res || res.length === 0);
};
const addFirstOrLookup = async (q) => {
	if (!q) return;
	const first = (state.lastProductResults || [])[0];
	if (first && (first.barcode === q || first.sku === q)) {
		await addToCart(first);
		qs("#productSearch").value = "";
		qs("#productResults").classList.add("d-none");
		return;
	}
	const res = await fetchJson(`/pos/api/product?code=${encodeURIComponent(q)}${warehouseParam()}`);
	if (!res.ok) {
		if ((state.lastProductResults || []).length) {
			await addToCart(state.lastProductResults[0]);
			qs("#productSearch").value = "";
			qs("#productResults").classList.add("d-none");
		}
		return;
	}
	const p = res.data;
	if (p?.id) {
		if (p.is_inactive) {
			showAlert(p.warning || "المنتج غير نشط.", "warning");
			return;
		}
		if (p.warning) showAlert(p.warning, "warning");
		await addToCart(p);
		qs("#productSearch").value = "";
		qs("#productResults").classList.add("d-none");
	} else {
		showAlert(res.error || "لم يُعثر على المنتج");
	}
};
const runProductSearch = async (q) => {
	if (!q) {
		qs("#productResults").classList.add("d-none");
		state.lastProductResults = [];
		qs("#productLoading").classList.add("d-none");
		return;
	}
	if (productBusy) return;
	productBusy = true;
	qs("#productLoading").classList.remove("d-none");
	const res = await fetchJson(`/pos/api/products?q=${encodeURIComponent(q)}${warehouseParam()}`);
	if (res.ok) renderProductResults(res.data);
	else showAlert(res.error || "فشل البحث");
	productBusy = false;
	qs("#productLoading").classList.add("d-none");
};
const loadCategories = async () => {
	const box = qs("#posCategories");
	if (!box) return;
	const res = await fetchJson("/pos/api/categories");
	console.log("LC res", res);
	if (!res.ok) return;
	const cats = res.data;
	console.log("LC cats", cats, typeof cats, Array.isArray(cats));
	if (!cats) return;
	let html = '<div class="pos-cat active" data-cat="">الكل</div>';
	cats.forEach((c) => {
		const name = c.name_ar || c.name;
		html += `<div class="pos-cat" data-cat="${c.id}">${esc(name)}</div>`;
	});
	box.innerHTML = html;
	box.querySelectorAll(".pos-cat").forEach((el) => {
		el.addEventListener("click", () => {
			box.querySelectorAll(".pos-cat").forEach((x) => void x.classList.remove("active"));
			el.classList.add("active");
			void loadProducts(el.getAttribute("data-cat"));
		});
	});
};
const loadProducts = async (categoryId) => {
	const grid = qs("#posProductGrid");
	if (!grid) return;
	grid.innerHTML =
		'<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i> جاري التحميل...</div>';
	try {
		const url =
			"/pos/api/products?per_page=60" +
			(categoryId ? `&category_id=${encodeURIComponent(categoryId)}` : "") +
			warehouseParam();
		const res = await fetchJson(url);
		if (!res.ok || !res.data?.length) {
			grid.innerHTML = '<div class="pos-cart-empty">لا توجد منتجات</div>';
			return;
		}
		grid.innerHTML = "";
		res.data.forEach((p) => {
			const card = document.createElement("div");
			card.className = `pos-card${p.is_out_of_stock ? " out" : ""}`;
			const badge = p.is_inactive
				? '<span class="badge danger">غير نشط</span>'
				: p.is_out_of_stock
					? '<span class="badge danger">نفد</span>'
					: p.stock <= 5
						? `<span class="badge warn">${fmt(p.stock)}</span>`
						: "";
			card.innerHTML = `
                    <div class="icon">📦</div>
                    <div class="name">${esc(p.name)}</div>
                    <div class="meta">
                        <span class="price">${fmt(priceForCurrency(p.price))} ${currencySymbolFor(selectedCurrency())}</span>
                        ${badge}
                    </div>
                `;
			card.addEventListener("click", async () => {
				if (p.is_inactive) {
					showAlert("المنتج غير نشط.", "warning");
					return;
				}
				await addToCart(p);
				qs("#productSearch").focus();
			});
			grid.appendChild(card);
		});
	} catch (_err) {
		grid.innerHTML = '<div class="pos-cart-empty">تعذر تحميل المنتجات</div>';
	}
};
const loadFloors = async () => {
	const box = qs("#posFloors");
	const _grid = qs("#posTablesGrid");
	const res = await fetchJson("/pos/api/floors");
	if (!res.ok) return;
	const floors = res.data;
	if (!floors?.length) {
		box.innerHTML = '<div class="pos-cart-empty">لا توجد أرضيات</div>';
	} else {
		box.innerHTML = floors
			.map((f) => `<div class="pos-cat" data-floor="${f.id}">${esc(f.name_ar || f.name)}</div>`)
			.join("");
		box.querySelectorAll(".pos-cat").forEach((el) => {
			el.addEventListener("click", () => {
				box.querySelectorAll(".pos-cat").forEach((x) => void x.classList.remove("active"));
				el.classList.add("active");
				void loadTables(el.getAttribute("data-floor"));
			});
		});
	}
};
const loadTables = async (floorId) => {
	const grid = qs("#posTablesGrid");
	grid.innerHTML = '<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i></div>';
	const res = await fetchJson(`/pos/api/floors/${floorId}/tables`);
	if (!res.ok) {
		grid.innerHTML = '<div class="pos-cart-empty">تعذر التحميل</div>';
		return;
	}
	const tables = res.data;
	if (!tables) {
		grid.innerHTML = '<div class="pos-cart-empty">تعذر التحميل</div>';
		return;
	}
	grid.innerHTML = "";
	tables.forEach((tbl) => {
		const occupied = tbl.status && tbl.status !== "free";
		const card = document.createElement("div");
		card.className = `pos-card${occupied ? " out" : ""}`;
		card.innerHTML = `<div class="icon">🪑</div><div class="name">${esc(tbl.label)}</div><div class="meta"><span class="price">${esc(tbl.status || "free")}</span></div>`;
		card.addEventListener("click", () => {
			state.selectedTable = { id: tbl.id, label: tbl.label };
			const sel = qs("#posTableSelected");
			if (sel) sel.textContent = `${t("الطاولة المحددة")} ${tbl.label}`;
			const tablesBtn = qs("#posTablesBtn");
			if (tablesBtn) tablesBtn.title = `${t("الطاولة")} ${tbl.label}`;
			if (window.jQuery) window.$("#posTablesModal").modal("hide");
		});
		grid.appendChild(card);
	});
};

export {
	addFirstOrLookup,
	customerHint,
	hideModalAlert,
	loadCategories,
	loadFloors,
	loadOrderTypes,
	loadProducts,
	loadTableOptions,
	loadTables,
	renderProductResults,
	runProductSearch,
	showAlert,
	showModalAlert,
	toggleTableField,
};
