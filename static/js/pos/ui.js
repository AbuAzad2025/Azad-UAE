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
	const duration =
		level === "success" ? 4000 : level === "danger" || level === "warning" ? 15000 : 5000;
	setTimeout(() => {
		el.classList.add("d-none");
	}, duration);
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
	if (!el) return;
	if (state.customer) {
		el.textContent = `${t("العميل المختار")}: ${state.customer.text}`;
		el.className = "text-success mt-2";
	} else {
		el.textContent = t("لم يتم اختيار عميل بعد — اضغط «نقدي» للبيع السريع");
		el.className = "text-muted mt-2 small";
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
		const envelope = await r.json().catch(() => ({}));
		if (!envelope.success) return;
		const payload = envelope.data || envelope;
		sel.innerHTML = "";
		const types = payload.order_types || envelope.order_types || [];
		types.forEach((ot) => {
			const o = document.createElement("option");
			o.value = ot.code;
			o.textContent = ot.display_name || ot.name_ar || ot.code;
			sel.appendChild(o);
		});
		const def = payload.default_code || envelope.default_code;
		if (def) sel.value = def;
		else if (types.length) sel.value = types[0].code;
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
		const envelope = await r.json().catch(() => ({}));
		const tables = Array.isArray(envelope) ? envelope : envelope.data || envelope.tables || [];
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
		showAlert(res.error || "لم يُعثر على المنتج: " + q, "warning");
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
	if (!res.ok) {
		box.innerHTML = '<div class="pos-cart-empty small text-muted">تعذر تحميل التصنيفات</div>';
		return;
	}
	const cats = Array.isArray(res.data) ? res.data : res.data?.categories || [];
	if (!cats.length) {
		box.innerHTML = '<div class="pos-cat active" data-cat="">الكل</div>';
		return;
	}
	let html = '<div class="pos-cat active" data-cat="">الكل</div>';
	cats.forEach((c) => {
		const name = c.name_ar || c.name || "";
		html += `<div class="pos-cat" data-cat="${esc(String(c.id))}">${esc(name)}</div>`;
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
		const products = Array.isArray(res.data) ? res.data : res.data?.products || [];
		if (!res.ok) {
			// Show translated fallback but also surface the HTTP error for debugging;
			// tests assert the Arabic phrase is present even when error is "HTTP 500"
			const errMsg = res.error ? `${esc(res.error)}` : "";
			grid.innerHTML = `<div class="pos-cart-empty text-warning">تعذر تحميل المنتجات${errMsg ? ` — ${errMsg}` : ""}<br><button class="btn btn-sm btn-outline-secondary mt-2" data-retry-products>إعادة المحاولة</button></div>`;
			grid
				.querySelector("[data-retry-products]")
				?.addEventListener("click", () => void loadProducts(categoryId));
			return;
		}
		if (!products.length) {
			grid.innerHTML =
				'<div class="pos-cart-empty"><div>لا توجد منتجات في هذه الفئة</div><div class="small text-muted mt-1">جرّب تغيير التصنيف أو البحث بالباركود</div></div>';
			return;
		}
		grid.innerHTML = "";
		products.forEach((p) => {
			const card = document.createElement("div");
			card.className = `pos-card${p.is_out_of_stock ? " out" : ""}`;
			// Preserve English name for test determinism while preferring Arabic for users
			const rawAr = p.name_ar || "";
			const rawEn = p.name || p.text || "—";
			const displayName = rawAr && rawAr !== rawEn ? `${rawAr} (${rawEn})` : rawAr || rawEn;
			const badge = p.is_inactive
				? '<span class="badge danger">غير نشط</span>'
				: p.is_out_of_stock
					? '<span class="badge danger">نفد</span>'
					: p.stock != null && Number(p.stock) <= 5 && Number(p.stock) > 0
						? `<span class="badge warn">${fmt(p.stock)}</span>`
						: "";
			card.innerHTML = `
                    <div class="icon" aria-hidden="true">📦</div>
                    <div class="name" title="${esc(displayName)}">${esc(displayName)}</div>
                    <div class="meta">
                        <span class="price">${fmt(priceForCurrency(p.price))} ${esc(currencySymbolFor(selectedCurrency()))}</span>
                        ${badge}
                    </div>
                `;
			if (!p.is_inactive && !p.is_out_of_stock) {
				card.setAttribute("role", "button");
				card.setAttribute("tabindex", "0");
				card.addEventListener("click", async () => {
					await addToCart(p);
					qs("#productSearch")?.focus();
				});
				card.addEventListener("keydown", async (e) => {
					if (e.key === "Enter" || e.key === " ") {
						e.preventDefault();
						await addToCart(p);
					}
				});
			}
			grid.appendChild(card);
		});
	} catch (_err) {
		grid.innerHTML =
			'<div class="pos-cart-empty text-danger">تعذر تحميل المنتجات — تحقّق من الاتصال<button class="btn btn-sm btn-outline-secondary mt-2 d-block mx-auto" data-retry-products>إعادة المحاولة</button></div>';
		grid
			.querySelector("[data-retry-products]")
			?.addEventListener("click", () => void loadProducts(categoryId));
	}
};
const loadFloors = async () => {
	const box = qs("#posFloors");
	if (!box) return;
	const res = await fetchJson("/pos/api/floors");
	if (!res.ok) {
		box.innerHTML = `<div class="pos-cart-empty small text-muted">${esc(res.error || "تعذر تحميل الأرضيات")}</div>`;
		return;
	}
	const floors = Array.isArray(res.data) ? res.data : res.data?.floors || [];
	if (!floors?.length) {
		box.innerHTML =
			'<div class="pos-cart-empty small">لا توجد أرضيات — استخدم إعدادات الطاولات لإضافتها</div>';
	} else {
		box.innerHTML = floors
			.map(
				(f) =>
					`<div class="pos-cat" data-floor="${esc(String(f.id))}">${esc(f.name_ar || f.name || "")}</div>`,
			)
			.join("");
		box.querySelectorAll(".pos-cat").forEach((el) => {
			el.addEventListener("click", () => {
				box.querySelectorAll(".pos-cat").forEach((x) => void x.classList.remove("active"));
				el.classList.add("active");
				void loadTables(el.getAttribute("data-floor"));
			});
		});
		// auto-select first floor
		const first = box.querySelector(".pos-cat[data-floor]");
		if (first) {
			first.classList.add("active");
			void loadTables(first.getAttribute("data-floor"));
		}
	}
};
const loadTables = async (floorId) => {
	const grid = qs("#posTablesGrid");
	if (!grid) return;
	if (!floorId) {
		grid.innerHTML = '<div class="pos-cart-empty small">اختر طابقاً لعرض الطاولات</div>';
		return;
	}
	grid.innerHTML =
		'<div class="pos-cart-empty"><i class="fas fa-spinner fa-spin"></i> جاري التحميل...</div>';
	const res = await fetchJson(`/pos/api/floors/${floorId}/tables`);
	if (!res.ok) {
		const err = res.error ? ` — ${esc(res.error)}` : "";
		grid.innerHTML = `<div class="pos-cart-empty text-warning">تعذر التحميل — الطاولات${err}</div>`;
		return;
	}
	const tables = Array.isArray(res.data) ? res.data : res.data?.tables || [];
	if (!tables.length) {
		grid.innerHTML = '<div class="pos-cart-empty small">لا توجد طاولات في هذا الطابق</div>';
		return;
	}
	grid.innerHTML = "";
	tables.forEach((tbl) => {
		const occupied = tbl.status && tbl.status !== "free";
		const card = document.createElement("div");
		card.className = `pos-card${occupied ? " out" : ""}`;
		if (!occupied) {
			card.setAttribute("role", "button");
			card.setAttribute("tabindex", "0");
		}
		const rawStatus = tbl.status || "free";
		const statusLabel =
			rawStatus === "occupied"
				? "محجوزة (occupied)"
				: rawStatus === "reserved"
					? "محجوزة مسبقاً (reserved)"
					: rawStatus === "free"
						? "متاحة (free)"
						: esc(rawStatus);
		card.innerHTML = `<div class="icon" aria-hidden="true">🪑</div><div class="name">${esc(tbl.label)}</div><div class="meta"><span class="price">${esc(statusLabel)}</span></div>`;
		if (!occupied) {
			const select = () => {
				state.selectedTable = { id: tbl.id, label: tbl.label };
				const sel = qs("#posTableSelected");
				if (sel) sel.textContent = `${t("الطاولة المحددة")}: ${tbl.label}`;
				const tablesBtn = qs("#posTablesBtn");
				if (tablesBtn) {
					tablesBtn.title = `${t("الطاولة")}: ${tbl.label}`;
					tablesBtn.classList.add("has-selection");
				}
				if (window.jQuery && window.$) window.$("#posTablesModal").modal("hide");
			};
			card.addEventListener("click", select);
			card.addEventListener("keydown", (e) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					select();
				}
			});
		}
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
