import { state, t, qs, fetchJson, warehouseParam } from './core.js';
import { addToCart } from './cart.js';
import { showAlert } from './ui.js';

const handleScannedCode = async (code) => {
	if (!code?.trim()) return;
	let p = null;
	try {
		const res = await fetchJson(
			`/pos/api/product?code=${encodeURIComponent(code.trim())}${warehouseParam()}`,
		);
		if (res.ok) p = res.data;
	} catch (_) {}
	if (!p && window.posOfflineCatalog) {
		p = await window.posOfflineCatalog.lookupLocalProduct(code.trim());
	}
	if (p?.id) {
		if (p.is_inactive) {
			showAlert(p.warning || "المنتج غير نشط.", "warning");
			return;
		}
		const liveKg = Number(state.scaleWeightKg) || 0;
		const qty = p.is_weight_product && liveKg > 0 ? liveKg : p.scale_weight_kg || 1;
		await addToCart(p, qty);
		qs("#productSearch").value = "";
		qs("#productResults").classList.add("d-none");
		showAlert(`${t("تمت إضافة")} ${p.name}`, "success");
	}
};
const setupDevices = () => {
	state.barcodeScanner = new window.BarcodeScanner({ onScan: handleScannedCode });
	state.barcodeScanner.start();
	if (window.setupCameraScanUI) {
		window.setupCameraScanUI({
			button: qs("#cameraScanBtn"),
			onScan: (code) => void handleScannedCode(code),
			onError: (msg) => showAlert(msg, "warning"),
		});
	}
	if (window.PosScaleSerial && window.setupPosScaleUI) {
		const scaleBtn = qs("#scaleConnectBtn");
		state.posScale = new window.PosScaleSerial({
			onStableWeight: (kg) => {
				state.scaleWeightKg = kg;
				if (scaleBtn) scaleBtn.dataset.liveWeight = kg.toFixed(3);
			},
			onError: (msg) => showAlert(msg, "warning"),
		});
		window.setupPosScaleUI({
			button: scaleBtn,
			scale: state.posScale,
			connectedTitle: scaleBtn?.dataset.scaleOnTitle,
		});
	}
	if (window.posOfflineCatalog) {
		const hydrate = () =>
			void window.posOfflineCatalog.hydrateCatalog({ warehouseParam: warehouseParam("?") });
		hydrate();
		window.addEventListener("online", hydrate);
	}
};
export { handleScannedCode, setupDevices };
