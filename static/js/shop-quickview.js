(() => {
	const modal = document.getElementById("ps-quick-view-modal");
	const body = document.getElementById("ps-quick-view-body");
	if (!modal || !body) return;
	const slug = document.body.getAttribute("data-store-slug");
	const closeBtn = modal.querySelector("[data-modal-close]");
	const overlay = modal.querySelector(".ps-modal-overlay");
	function openModal(productId) {
		body.innerHTML =
			'<div class="ps-modal-loading"><i class="fas fa-spinner fa-spin"></i> Loading...</div>';
		modal.style.display = "flex";
		document.body.style.overflow = "hidden";
		fetch("/s/" + slug + "/quick-view/" + productId, {
			headers: { "X-Requested-With": "XMLHttpRequest" },
		})
			.then((r) => r.text())
			.then((html) => {
				body.innerHTML = html;
				const minusBtns = body.querySelectorAll("[data-qty-minus]");
				const plusBtns = body.querySelectorAll("[data-qty-plus]");
				minusBtns.forEach((btn) => {
					btn.addEventListener("click", () => {
						const input = btn
							.closest(".ps-qty-wrap")
							?.querySelector('input[type="number"]');
						if (!input) return;
						const val = parseFloat(input.value || "1");
						const min = parseFloat(input.min || "1");
						input.value = Math.max(min, val - 1);
					});
				});
				plusBtns.forEach((btn) => {
					btn.addEventListener("click", () => {
						const input = btn
							.closest(".ps-qty-wrap")
							?.querySelector('input[type="number"]');
						if (!input) return;
						const val = parseFloat(input.value || "1");
						const max = parseFloat(input.max || "9999");
						input.value = Math.min(max, val + 1);
					});
				});
				const forms = body.querySelectorAll("[data-ajax-cart]");
				forms.forEach((f) => {
					f.addEventListener("submit", (e) => {
						e.preventDefault();
						const pid = f.querySelector('[name="product_id"]')?.value;
						const qty = f.querySelector('[name="quantity"]')?.value || 1;
						if (window.ShopCart && window.ShopCart.addToCart) {
							void window.ShopCart.addToCart(parseInt(pid), parseFloat(qty));
						}
					});
				});
			});
	}
	function closeModal() {
		modal.style.display = "none";
		document.body.style.overflow = "";
	}
	if (closeBtn) closeBtn.addEventListener("click", closeModal);
	if (overlay) overlay.addEventListener("click", closeModal);
	document.addEventListener("keydown", (e) => {
		if (e.key === "Escape") closeModal();
	});
	document.addEventListener("click", (e) => {
		const btn = e.target.closest("[data-quick-view]");
		if (!btn) return;
		e.preventDefault();
		const pid = btn.getAttribute("data-product-id");
		if (pid) openModal(parseInt(pid));
	});
	window.ShopQuickView = { open: openModal, close: closeModal };
})();
