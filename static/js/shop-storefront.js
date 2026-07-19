(() => {
	document.addEventListener("click", (e) => {
		const btn = e.target.closest("[data-qty-minus], [data-qty-plus]");
		if (!btn) return;
		const input = btn
			.closest(".ps-qty-wrap")
			?.querySelector('input[type="number"]');
		if (!input) return;
		const step = parseFloat(input.step || "1") || 1;
		const min = parseFloat(input.min || "1") || 1;
		const max = parseFloat(input.max || "9999") || 9999;
		let val = parseFloat(input.value) || min;
		if (btn.hasAttribute("data-qty-minus")) val = Math.max(min, val - step);
		else val = Math.min(max, val + step);
		input.value = String(val);
		const evt = new Event("change", { bubbles: true });
		input.dispatchEvent(evt);
	});

	const navToggle = document.querySelector(".ps-nav-toggle");
	const nav = document.querySelector(".ps-nav");
	if (navToggle && nav) {
		navToggle.addEventListener("click", () => {
			const isOpen = nav.classList.contains("is-open");
			if (isOpen) {
				nav.style.height = nav.scrollHeight + "px";
				requestAnimationFrame(() => {
					nav.classList.remove("is-open");
					nav.style.height = "0";
				});
			} else {
				nav.classList.add("is-open");
				nav.style.height = nav.scrollHeight + "px";
				nav.addEventListener("transitionend", function handler() {
					nav.style.height = "";
					nav.removeEventListener("transitionend", handler);
				});
			}
			navToggle.setAttribute("aria-expanded", isOpen ? "false" : "true");
		});
	}

	const alerts = document.querySelectorAll(".ps-alert[data-auto-dismiss]");
	alerts.forEach((el) => {
		setTimeout(() => {
			el.style.transition = "opacity 0.4s";
			el.style.opacity = "0";
			setTimeout(() => {
				el.remove();
			}, 400);
		}, 5000);
	});

	const searchInput = document.querySelector(
		'.ps-search-form input[type="search"]:not([data-search-autocomplete])',
	);
	if (searchInput) {
		const searchForm = searchInput.closest("form");
		let searchTimer;
		searchInput.addEventListener("input", () => {
			clearTimeout(searchTimer);
			searchTimer = setTimeout(() => {
				if (searchForm) searchForm.submit();
			}, 300);
		});
	}

	const cartUpdateForm = document.getElementById("cart-update-form");
	if (cartUpdateForm) {
		cartUpdateForm.querySelectorAll('input[type="number"]').forEach((input) => {
			input.addEventListener("change", () => {
				const data = {};
				const formData = new FormData(cartUpdateForm);
				formData.forEach((value, key) => {
					data[key] = value;
				});
				if (window.ShopCart && window.ShopCart.updateCart) {
					void window.ShopCart.updateCart(data);
				}
			});
		});
	}

	let deferredPrompt;
	window.addEventListener("beforeinstallprompt", (e) => {
		e.preventDefault();
		deferredPrompt = e;
		const banner = document.getElementById("ps-install-banner");
		if (banner) banner.style.display = "flex";
	});

	const sentinel = document.querySelector(".ps-infinite-sentinel");
	if (sentinel) {
		let currentPage = parseInt(sentinel.getAttribute("data-page") || "1");
		const totalPages = parseInt(sentinel.getAttribute("data-total") || "1");
		let loading = false;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && !loading && currentPage < totalPages) {
					loading = true;
					const nextPage = currentPage + 1;
					const url = new URL(window.location.href);
					url.searchParams.set("page", String(nextPage));
					fetch(url.toString(), {
						headers: { "X-Requested-With": "XMLHttpRequest" },
					})
						.then((r) => r.text())
						.then((html) => {
							const parser = new DOMParser();
							const doc = parser.parseFromString(html, "text/html");
							const newItems = doc.querySelectorAll(".ps-card");
							const grid = document.querySelector(".ps-grid");
							if (grid && newItems.length) {
								newItems.forEach((item) => {
									grid.appendChild(item);
								});
							}
							currentPage = nextPage;
							if (currentPage >= totalPages) {
								sentinel.style.display = "none";
							}
							sentinel.setAttribute("data-page", currentPage);
							loading = false;
						})
						.catch(() => {
							loading = false;
						});
				}
			},
			{ threshold: 0.1 },
		);
		observer.observe(sentinel);
	}
})();
