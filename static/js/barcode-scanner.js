class BarcodeScanner {
	constructor(options = {}) {
		this.onScan = options.onScan || (() => {});
		this.buffer = "";
		this.timeout = null;
		this.scanDelay = options.scanDelay || 100;
		this.minLength = options.minLength || 3;
		this.active = false;
		this._boundHandleKeyPress = this.handleKeyPress.bind(this);
	}

	start() {
		this.active = true;
		document.addEventListener("keypress", this._boundHandleKeyPress);
	}

	stop() {
		this.active = false;
		document.removeEventListener("keypress", this._boundHandleKeyPress);
	}

	handleKeyPress(e) {
		if (!this.active) return;

		if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") {
			if (!e.target.classList.contains("barcode-input")) {
				return;
			}
		}

		if (e.key === "Enter") {
			if (this.buffer.length >= this.minLength) {
				this.onScan(this.buffer);
			}
			this.buffer = "";
			clearTimeout(this.timeout);
			return;
		}

		this.buffer += e.key;

		clearTimeout(this.timeout);
		this.timeout = setTimeout(() => {
			this.buffer = "";
		}, this.scanDelay);
	}
}

class CameraBarcodeScanner {
	constructor(videoElement, options = {}) {
		this.video = videoElement;
		this.onScan = options.onScan || (() => {});
		this.onError = options.onError || ((msg) => alert(msg));
		this.isScanning = false;
		this.stream = null;
		this.detector = null;
		this._timer = null;
		this._lastCode = null;
		this._lastCodeAt = 0;
		this.scanIntervalMs = options.scanIntervalMs || 350;
		this.duplicateCooldownMs = options.duplicateCooldownMs || 2500;
	}

	static isSupported() {
		return Boolean(
			navigator.mediaDevices?.getUserMedia &&
				(window.BarcodeDetector || window.CameraBarcodeScannerForceJsQr),
		);
	}

	async start() {
		if (!window.BarcodeDetector) {
			this.onError(
				"مسح الباركود بالكاميرا غير مدعوم في هذا المتصفح — استخدم قارئ الباركود أو الإدخال اليدوي",
			);
			return false;
		}
		try {
			const formats = await window.BarcodeDetector.getSupportedFormats();
			const wanted = [
				"ean_13",
				"ean_8",
				"upc_a",
				"upc_e",
				"code_128",
				"code_39",
				"qr_code",
				"data_matrix",
			];
			const accepted = wanted.filter((f) => formats.includes(f));
			this.detector = new window.BarcodeDetector(
				accepted.length ? { formats: accepted } : undefined,
			);
			this.stream = await navigator.mediaDevices.getUserMedia({
				video: { facingMode: "environment", width: { ideal: 1280 } },
				audio: false,
			});
			this.video.srcObject = this.stream;
			await this.video.play();
			this.isScanning = true;
			this._scheduleNext();
			return true;
		} catch (_error) {
			this.onError("لا يمكن الوصول إلى الكاميرا");
			this.stop();
			return false;
		}
	}

	stop() {
		this.isScanning = false;
		if (this._timer) {
			clearTimeout(this._timer);
			this._timer = null;
		}
		if (this.stream) {
			this.stream.getTracks().forEach((track) => void track.stop());
			this.stream = null;
		}
		this.video.srcObject = null;
	}

	_scheduleNext() {
		if (!this.isScanning) return;
		this._timer = setTimeout(() => void this.scan(), this.scanIntervalMs);
	}

	async scan() {
		if (!this.isScanning) return;
		try {
			if (this.video.readyState === this.video.HAVE_ENOUGH_DATA) {
				const code = await this.detectBarcode(this.video);
				if (code) {
					const now = Date.now();
					const isDuplicate =
						code === this._lastCode && now - this._lastCodeAt < this.duplicateCooldownMs;
					if (!isDuplicate) {
						this._lastCode = code;
						this._lastCodeAt = now;
						this.onScan(code);
						this.stop();
						return;
					}
				}
			}
		} catch (_error) {
			/* transient decode failure — keep scanning */
		}
		this._scheduleNext();
	}

	async detectBarcode(source) {
		if (!this.detector) return null;
		const barcodes = await this.detector.detect(source);
		if (!barcodes || barcodes.length === 0) return null;
		const value = (barcodes[0].rawValue || "").trim();
		return value || null;
	}
}

window.BarcodeScanner = BarcodeScanner;
window.CameraBarcodeScanner = CameraBarcodeScanner;

/**
 * Wire a camera-scan button to a lazy-created fullscreen overlay with a live
 * video preview. Returns null when camera scanning is unsupported so callers
 * can hide the button. Shared by both POS registers to avoid duplicated UI.
 */
function setupCameraScanUI({ button, onScan, onError }) {
	if (!button) return null;
	if (!CameraBarcodeScanner.isSupported()) {
		button.classList.add("d-none");
		return null;
	}

	let overlay = null;
	let scanner = null;
	let open = false;

	const buildOverlay = () => {
		const el = document.createElement("div");
		el.id = "cameraScanOverlay";
		el.style.cssText =
			"position:fixed;inset:0;z-index:2000;background:rgba(0,0,0,.85);" +
			"display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;";
		const video = document.createElement("video");
		video.id = "cameraScanVideo";
		video.muted = true;
		video.playsInline = true;
		video.style.cssText = "width:min(92vw,640px);border-radius:12px;background:#000;";
		const hint = document.createElement("div");
		hint.style.cssText = "color:#fff;font-size:1rem;";
		hint.textContent = button.getAttribute("data-scan-hint") || "وجّه الكاميرا نحو الباركود";
		const closeBtn = document.createElement("button");
		closeBtn.type = "button";
		closeBtn.textContent = "✕";
		closeBtn.setAttribute("aria-label", "Close");
		closeBtn.style.cssText =
			"position:absolute;top:16px;inset-inline-end:16px;font-size:1.4rem;color:#fff;" +
			"background:transparent;border:0;cursor:pointer;padding:8px;";
		closeBtn.addEventListener("click", () => stop());
		el.append(video, hint, closeBtn);
		document.body.appendChild(el);
		return { el, video };
	};

	const stop = () => {
		open = false;
		if (scanner) scanner.stop();
		if (overlay) overlay.el.style.display = "none";
	};

	const startScan = async () => {
		if (open) return;
		if (!overlay) overlay = buildOverlay();
		overlay.el.style.display = "flex";
		open = true;
		scanner = new CameraBarcodeScanner(overlay.video, {
			onScan: (code) => {
				stop();
				onScan(code);
			},
			onError: (msg) => {
				stop();
				if (onError) onError(msg);
			},
		});
		const started = await scanner.start();
		if (!started) stop();
	};

	button.addEventListener("click", () => void startScan());
	return { stop };
}

window.setupCameraScanUI = setupCameraScanUI;
