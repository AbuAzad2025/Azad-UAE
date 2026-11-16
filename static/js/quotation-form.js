(() => {
	const container = document.getElementById("lines-container");
	if (!container) return;

	let lineIndex = parseInt(container.dataset.nextIndex || "0", 10) || 0;
	const autoAdd = container.dataset.autoAdd === "1";

	// The customer's type drives the suggested unit price (merchant => merchant price).
	function customerType() {
		const $sel = $("#f_customer_id");
		if (!$sel.length) return "regular";
		const data = $sel.select2 ? $sel.select2("data") : [];
		if (data?.length && data[0]?.customer_type) {
			return data[0].customer_type;
		}
		const opt = $sel.find("option:selected");
		return (opt.data("customer-type") || "regular").toString();
	}

	function initProductSelect($sel) {
		if (!$sel.length) return;
		if ($sel.hasClass("select2-hidden-accessible")) {
			$select2Destroy($sel);
		}
		const line = $sel.data("line");
		const $wh = container.querySelector
			? $(container).find(`.wh-select[data-line="${line}"]`)
			: null;
		const wid = $wh?.val() || "";
		const searchUrl = wid ? `/api/warehouses/${wid}/products` : "/api/v2/products/search";

		$sel.select2({
			ajax: {
				url: searchUrl,
				dataType: "json",
				delay: 300,
				data: (params) => ({ q: params.term || "", page: params.page || 1 }),
				processResults: (data) => {
					const items = Array.isArray(data) ? data : data?.data || data.results || [];
					return {
						results: items.map((item) => ({
							id: item.id,
							text: item.text ? item.text : `${item.name || ""}${item.sku ? ` (${item.sku})` : ""}`,
							name: item.name || "",
							sku: item.sku || "",
							price: item.price || 0,
							merchant_price: item.merchant_price || null,
							cost_price: item.cost_price || 0,
							stock: item.stock || 0,
						})),
						pagination: { more: false },
					};
				},
				cache: true,
			},
			placeholder: window.t ? window.t("Search_Product") : "Search product",
			allowClear: true,
			minimumInputLength: 0,
			dir: "rtl",
			width: "100%",
		});

		$sel.on("select2:select", (e) => {
			const item = e.params.data;
			const $row = $sel.closest(".quotation-line");
			const priceInput = $row.find('input[name$="-unit_price"]');
			const hint = $row.find(".price-hint");
			const costSpan = hint.find(".cost-val");
			const marginSpan = hint.find(".margin-val");
			const useBtn = hint.find(".use-cost-margin");

			// Suggested price based on the customer type.
			const isMerchant = customerType() === "merchant";
			let suggested = item.price || 0;
			if (isMerchant && item.merchant_price) {
				suggested = item.price * (1 - item.merchant_price / 100);
			}
			if (priceInput.length) {
				priceInput.val(suggested.toFixed(2));
			}

			// Hint: cost price + margin.
			const cost = parseFloat(item.cost_price || 0);
			const price = parseFloat(item.price || 0);
			const margin = price > 0 ? (((price - cost) / price) * 100).toFixed(1) : "0.0";
			costSpan.text(cost.toFixed(2));
			marginSpan.text(margin);
			useBtn.data("cost", cost);
			useBtn.data("margin", margin);
		});
	}

	function $select2Destroy($sel) {
		try {
			$sel.select2("destroy");
		} catch {
			/* noop */
		}
	}

	function reinitProductSelect($sel) {
		const line = $sel.data("line");
		const $wh = $(container).find(`.wh-select[data-line="${line}"]`);
		const wid = $wh?.val() || "";
		// Destroy + recreate by toggling the data attribute used by initProductSelect
		$sel.removeData("wh");
		$sel.data("wh", wid);
		initProductSelect($sel);
	}

	function addLine() {
		const tpl = document.getElementById("quotation-line-template");
		if (!tpl || !container) return;
		const html = tpl.innerHTML.replace(/__IDX__/g, String(lineIndex));
		const wrapper = document.createElement("div");
		wrapper.innerHTML = html.trim();
		const node = wrapper.firstElementChild;
		if (node) {
			container.appendChild(node);
			const $prod = $(node).find(".product-select");
			const $wh = $(node).find(".wh-select");
			// warehouse change -> re-init product select with the right search URL
			$wh.on("change", () => reinitProductSelect($prod));
			// use cost + margin button
			$(node)
				.find(".use-cost-margin")
				.on("click", function () {
					const cost = parseFloat($(this).data("cost") || 0);
					const margin = parseFloat($(this).data("margin") || 0) / 100;
					const price = cost * (1 + margin);
					const $row = $(this).closest(".quotation-line");
					$row.find('input[name$="-unit_price"]').val(price.toFixed(2));
				});
			lineIndex += 1;
		}
	}

	function removeLine(idx) {
		const el = container.querySelector(`[data-index="${idx}"]`);
		if (el) el.remove();
	}

	window.addLine = addLine;
	window.removeLine = removeLine;

	// Auto-init Select2 on customer select (already handled by customer-select.js,
	// but re-run here to be safe in case it loaded after us).
	function initCustomerSelect() {
		if (typeof window.initCustomerSelect === "function") {
			window.initCustomerSelect();
		}
	}

	// Initialize product selects already in the DOM (edit mode).
	function initExistingLines() {
		$(container)
			.find(".product-select")
			.each(function () {
				initProductSelect($(this));
			});
		$(container)
			.find(".wh-select")
			.each(function () {
				const line = $(this).data("line");
				const $prod = $(container).find(`.product-select[data-line="${line}"]`);
				$(this).on("change", () => reinitProductSelect($prod));
			});
		$(container)
			.find(".use-cost-margin")
			.each(function () {
				$(this).on("click", function () {
					const cost = parseFloat($(this).data("cost") || 0);
					const margin = parseFloat($(this).data("margin") || 0) / 100;
					const price = cost * (1 + margin);
					const $row = $(this).closest(".quotation-line");
					$row.find('input[name$="-unit_price"]').val(price.toFixed(2));
				});
			});
	}

	$(document).ready(() => {
		setTimeout(() => {
			initCustomerSelect();
			initExistingLines();
			if (autoAdd) {
				addLine();
			}
		}, 250);
	});
})();
