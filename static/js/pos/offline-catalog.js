/**
 * Offline product catalog for the POS register.
 *
 * Hydrates an IndexedDB snapshot from /pos/api/catalog/snapshot while
 * online; when the network drops, barcode/SKU resolution falls back to the
 * local snapshot so scanning keeps working. Includes a local mirror of the
 * server-side prefix-20 scale-barcode parser for offline weight items.
 */
/* global module, indexedDB */

const CATALOG_DB = "pos-catalog";
const CATALOG_STORE = "products";
const SCALE_PREFIX = "20";

/**
 * Local mirror of utils/pos_helpers.parse_scale_barcode: 13-digit EAN with
 * prefix 20 → { itemCode, weightKg } or null.
 */
function parseScaleBarcodeLocal(code) {
	const raw = String(code || "").trim();
	if (raw.length !== 13 || !/^\d+$/.test(raw) || !raw.startsWith(SCALE_PREFIX)) return null;
	const body = raw
		.slice(0, 12)
		.split("")
		.map((d) => Number(d));
	const checksum =
		(10 -
			((body.filter((_, i) => i % 2 === 0).reduce((a, b) => a + b, 0) +
				3 * body.filter((_, i) => i % 2 === 1).reduce((a, b) => a + b, 0)) %
				10)) %
		10;
	if (checksum !== Number(raw[12])) return null;
	const grams = Number(raw.slice(7, 12));
	return { itemCode: raw.slice(2, 7), weightKg: Math.round(grams) / 1000 };
}

function openCatalogDB() {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(CATALOG_DB, 1);
		req.onupgradeneeded = () => {
			const store = req.result.createObjectStore(CATALOG_STORE, { keyPath: "id" });
			store.createIndex("barcode_lc", "barcode_lc", { unique: false });
			store.createIndex("sku_lc", "sku_lc", { unique: false });
		};
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

function _normalize(product) {
	return {
		...product,
		barcode_lc: String(product.barcode || "").toLowerCase(),
		sku_lc: String(product.sku || "").toLowerCase(),
	};
}

/**
 * Fetch the server snapshot and replace the local catalog. Resolves with
 * the stored count; resolves 0 when offline or the endpoint fails.
 */
async function hydrateCatalog({ warehouseParam = "" } = {}) {
	try {
		const res = await fetch(`/pos/api/catalog/snapshot${warehouseParam}`, {
			credentials: "same-origin",
		});
		const data = await res.json().catch(() => ({}));
		if (!res.ok || !data.success || !Array.isArray(data.products)) return 0;
		const db = await openCatalogDB();
		const tx = db.transaction(CATALOG_STORE, "readwrite");
		const store = tx.objectStore(CATALOG_STORE);
		store.clear();
		for (const p of data.products) store.put(_normalize(p));
		await new Promise((resolve, reject) => {
			tx.oncomplete = resolve;
			tx.onerror = () => reject(tx.error);
		});
		return data.products.length;
	} catch {
		return 0;
	}
}

function _lookupByIndex(store, index, value) {
	return new Promise((resolve) => {
		const req = store.index(index).get(value);
		req.onsuccess = () => resolve(req.result || null);
		req.onerror = () => resolve(null);
	});
}

/**
 * Resolve a scanned code against the local snapshot. Handles plain
 * barcode/SKU matches and prefix-20 weight-embedded codes. Returns a
 * serialize_pos_product-shaped object or null.
 */
async function lookupLocalProduct(code) {
	const raw = String(code || "").trim();
	if (!raw) return null;
	let db;
	try {
		db = await openCatalogDB();
	} catch {
		return null;
	}
	const tx = db.transaction(CATALOG_STORE, "readonly");
	const store = tx.objectStore(CATALOG_STORE);
	const lc = raw.toLowerCase();
	let hit = await _lookupByIndex(store, "barcode_lc", lc);
	if (!hit) hit = await _lookupByIndex(store, "sku_lc", lc);
	let scale = null;
	if (!hit) {
		scale = parseScaleBarcodeLocal(raw);
		if (scale) {
			const itemLc = scale.itemCode.toLowerCase();
			hit = await _lookupByIndex(store, "barcode_lc", itemLc);
			if (!hit) hit = await _lookupByIndex(store, "sku_lc", itemLc);
			if (!hit) hit = await _lookupByIndex(store, "barcode_lc", `${SCALE_PREFIX}${itemLc}`);
		}
	}
	if (!hit) return null;
	const product = { ...hit };
	delete product.barcode_lc;
	delete product.sku_lc;
	product.success = true;
	if (scale && scale.weightKg > 0) {
		product.is_scale_item = true;
		product.scale_weight_kg = scale.weightKg;
	}
	return product;
}

if (typeof window !== "undefined") {
	window.posOfflineCatalog = { hydrateCatalog, lookupLocalProduct, parseScaleBarcodeLocal };
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { parseScaleBarcodeLocal };
}
