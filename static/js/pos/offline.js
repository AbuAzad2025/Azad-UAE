(() => {
	let swRegistration = null;
	let offlineStatusBar = null;
	let connectivityTimer = null;
	let lastOnlineState = true;

	function createOfflineBar() {
		if (document.getElementById("posOfflineBar")) return;
		const bar = document.createElement("div");
		bar.id = "posOfflineBar";
		bar.className =
			"alert alert-danger d-flex justify-content-between align-items-center py-2 mb-2 d-none";
		bar.setAttribute("role", "alert");
		bar.setAttribute("aria-live", "polite");
		bar.innerHTML =
			'<div><i class="fas fa-wifi mr-1"></i> <span id="posOfflineMsg">أنت غير متصل — الفواتير سيتم حفظها محلياً وإرسالها تلقائياً عند عودة الاتصال</span></div>' +
			'<button id="retryQueueBtn" type="button" class="btn btn-sm btn-light"><i class="fas fa-sync mr-1"></i>إعادة المحاولة</button>';
		// Insert above the POS grid for high visibility; fallback to session bar sibling.
		const posApp = document.querySelector(".pos-app");
		const posGrid = document.querySelector(".pos-grid");
		const sessionBar = document.getElementById("posSessionBar");
		if (posGrid && posApp) {
			posApp.insertBefore(bar, posGrid);
		} else if (sessionBar?.parentNode) {
			sessionBar.parentNode.insertBefore(bar, sessionBar.nextSibling);
		} else {
			(document.querySelector(".pos-fullscreen") || document.body).prepend(bar);
		}
		offlineStatusBar = bar;
	}

	function setOfflineVisible(visible, message) {
		if (!offlineStatusBar) return;
		if (message) {
			const msgEl = document.getElementById("posOfflineMsg");
			if (msgEl) msgEl.textContent = message;
		}
		offlineStatusBar.classList.toggle("d-none", !visible);
		// For consumers that check navigator.onLine, expose a data attribute
		document.documentElement.dataset.posOnline = visible ? "false" : "true";
	}

	async function probeConnectivity(timeoutMs = 3500) {
		// navigator.onLine is unreliable (captive portals, DNS hijack). Probe the
		// POS health endpoint with a short timeout; any HTTP response (even 401/403)
		// proves the server is reachable → online. Only network failures → offline.
		const ctrl = new AbortController();
		const t = setTimeout(() => ctrl.abort(), timeoutMs);
		try {
			const res = await fetch("/pos/api/session/current", {
				method: "GET",
				credentials: "same-origin",
				headers: { Accept: "application/json" },
				signal: ctrl.signal,
				cache: "no-store",
			});
			// Any HTTP response means we reached the server
			return res.status !== 0;
		} catch (_) {
			// Network error / abort → probe fallback endpoint quickly
			try {
				const ctrl2 = new AbortController();
				const t2 = setTimeout(() => ctrl2.abort(), 1500);
				const res2 = await fetch("/pos/api/products?per_page=1", {
					method: "GET",
					credentials: "same-origin",
					headers: { Accept: "application/json" },
					signal: ctrl2.signal,
					cache: "no-store",
				}).finally(() => clearTimeout(t2));
				return res2.status !== 0;
			} catch (_) {
				return false;
			}
		} finally {
			clearTimeout(t);
		}
	}

	function updateOnlineStatus() {
		if (!offlineStatusBar) return true;
		// Immediate synchronous visibility based on navigator.onLine so that
		// online/offline events reflect instantly (important for tests and UX).
		const navOnline = navigator.onLine;
		setOfflineVisible(!navOnline);
		// Asynchronous ground-truth probe — corrects the banner when
		// navigator.onLine is unreliable (captive portals, DNS hijack).
		void probeConnectivity()
			.then((probedOnline) => {
				// If probe says offline while navigator says online, trust probe.
				// If navigator says offline, probe may still confirm offline or
				// reveal we are actually online (e.g. navigator stale).
				const finalOnline = probedOnline;
				const wasOffline = !lastOnlineState;
				lastOnlineState = finalOnline;
				setOfflineVisible(!finalOnline);
				if (finalOnline && wasOffline) retryQueue();
			})
			.catch(() => {
				// Probe failed — keep navigator-based state
				lastOnlineState = navOnline;
			});
		return navOnline;
	}

	function registerSW() {
		if (!("serviceWorker" in navigator)) return;
		// For the POS the ServiceWorker must intersect /pos/api/*.
		// The script lives at /static/pos-sw.js; scope "/" is ideal (covers all)
		// but requires Service-Worker-Allowed: "/" on the response. Scope "/pos/"
		// is the legacy expected value in tests — we try it first for backward
		// compatibility, then fall back to "/" and finally the default scope.
		const tryRegister = (scope) =>
			navigator.serviceWorker
				.register("/static/pos-sw.js", scope ? { scope } : undefined)
				.then((reg) => {
					swRegistration = reg;
					if (navigator.serviceWorker.controller) {
						navigator.serviceWorker.addEventListener("message", () => {
							updateOnlineStatus();
						});
					}
					return reg;
				});

		// Legacy "/pos/" first keeps existing vitest expectations green, then
		// "/" for broader coverage, then default.
		tryRegister("/pos/")
			.catch(() => tryRegister("/"))
			.catch(() => tryRegister(null))
			.catch((err) => {
				if (window.console && console.debug) console.debug("POS SW registration failed:", err);
			});
	}

	function retryQueue() {
		let attempted = false;
		if (swRegistration?.active) {
			try {
				swRegistration.active.postMessage("retry-queue");
				attempted = true;
			} catch (_) {}
			if (swRegistration.sync) {
				swRegistration.sync.register("pos-queue-retry").catch(() => {});
				attempted = true;
			}
		}
		// Also poke any foreground offline-sync retry (for browsers without SW)
		if (navigator.serviceWorker?.controller) {
			try {
				navigator.serviceWorker.controller.postMessage("retry-queue");
				attempted = true;
			} catch (_) {}
		}
		// Visual feedback on the retry button
		const btn = document.getElementById("retryQueueBtn");
		if (btn) {
			const orig = btn.innerHTML;
			btn.disabled = true;
			btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i>جاري التحقّق...';
			// Kick a probe for ground truth, then restore button
			void probeConnectivity()
				.then((online) => setOfflineVisible(!online))
				.catch(() => {})
				.finally(() => {
					setTimeout(() => {
						btn.disabled = false;
						btn.innerHTML = orig;
					}, 1200);
				});
		}
		// If SW was never registered, still re-probe connectivity
		if (!attempted) updateOnlineStatus();
	}

	document.addEventListener("DOMContentLoaded", () => {
		createOfflineBar();
		registerSW();
		void updateOnlineStatus();

		// Periodic ground-truth probe (every 15s) — complements online/offline events
		connectivityTimer = setInterval(() => void updateOnlineStatus(), 15000);

		window.addEventListener("online", () => void updateOnlineStatus());
		window.addEventListener("offline", () => void updateOnlineStatus());
		// Also probe when tab becomes visible (user switches back)
		document.addEventListener("visibilitychange", () => {
			if (document.visibilityState === "visible") void updateOnlineStatus();
		});
		document.addEventListener("click", (e) => {
			const t = e.target;
			if (t && (t.id === "retryQueueBtn" || t.closest?.("#retryQueueBtn"))) {
				e.preventDefault();
				retryQueue();
			}
		});
		// Clean up interval on page unload
		window.addEventListener("beforeunload", () => {
			if (connectivityTimer) clearInterval(connectivityTimer);
		});
	});

	// Expose for manual retry and for tests
	window.__posOffline = {
		retryQueue,
		updateOnlineStatus,
		probeConnectivity,
		get swRegistration() {
			return swRegistration;
		},
	};
})();
