// AI-Enhanced Sales Form
// Auto-pricing, stock alerts, and smart recommendations

$(document).ready(() => {
	function getCsrfToken() {
		return document.querySelector('meta[name="csrf-token"]')?.content || "";
	}

	// Escape untrusted server/AI-provided strings before injecting into HTML
	// (defense against stored-XSS / prompt-injection-to-XSS).
	function esc(v) {
		return String(v == null ? "" : v)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;")
			.replace(/'/g, "&#39;");
	}

	// توصية السعر عند اختيار منتج وعميل
	function checkPriceRecommendation(productId, customerId, lineIndex) {
		if (!productId || !customerId) return;

		$.ajax({
			url: "/ai/recommend-price",
			method: "POST",
			contentType: "application/json",
			headers: { "X-CSRFToken": getCsrfToken() },
			data: JSON.stringify({
				product_id: productId,
				customer_id: customerId,
			}),
			success: (response) => {
				const priceInput = $(`#unit_price_${lineIndex}`);
				const currentPrice = parseFloat(priceInput.val()) || 0;

				if (currentPrice === 0 || Math.abs(currentPrice - response.recommended_price) > 0.01) {
					// إظهار توصية
					const badge = `
                        <span class="badge badge-info ai-recommendation" style="margin-right: 5px;">
                            <i class="fas fa-robot"></i> موصى به: ${response.recommended_price.toFixed(2)}
                            <button type="button" class="btn btn-xs btn-light ml-1" onclick="applyRecommendedPrice(${lineIndex}, ${response.recommended_price})">
                                تطبيق
                            </button>
                        </span>
                    `;

					priceInput.parent().find(".ai-recommendation").remove();
					priceInput.after(badge);
				}
			},
			error: () => {},
		});
	}

	// فحص المخزون
	function checkStockAlert(productId, quantity, lineIndex) {
		if (!productId || !quantity) return;

		$.ajax({
			url: "/ai/check-stock",
			method: "POST",
			contentType: "application/json",
			headers: { "X-CSRFToken": getCsrfToken() },
			data: JSON.stringify({
				product_id: productId,
				quantity: quantity,
			}),
			success: (response) => {
				const alertContainer = $(`#stock_alert_${lineIndex}`);
				alertContainer.empty();

				if (response.type === "error") {
					alertContainer.html(`
                        <div class="alert alert-danger alert-sm mt-2">
                            <i class="fas fa-exclamation-triangle"></i> ${esc(response.message)}
                        </div>
                    `);
				} else if (response.type === "warning") {
					alertContainer.html(`
                        <div class="alert alert-warning alert-sm mt-2">
                            <i class="fas fa-exclamation-circle"></i> ${esc(response.message)}
                        </div>
                    `);
				}
			},
		});
	}

	// تحليل سلوك العميل
	function analyzeCustomer(customerId) {
		if (!customerId) return;

		$.ajax({
			url: `/ai/analyze-customer/${customerId}`,
			method: "GET",
			success: (analysis) => {
				let riskClass = "info";
				if (analysis.risk_level === "high") riskClass = "danger";
				else if (analysis.risk_level === "medium") riskClass = "warning";

				const analysisHtml = `
                    <div class="alert alert-${riskClass} mt-3">
                        <h5><i class="fas fa-chart-line"></i> تحليل العميل</h5>
                        <p><strong>الرصيد الحالي:</strong> ${analysis.current_balance.toFixed(2)} درهم</p>
                        <p><strong>متوسط تأخير الدفع:</strong> ${analysis.avg_payment_delay_days} يوم</p>
                        <p><strong>التوصية:</strong> ${esc(analysis.recommendation)}</p>
                    </div>
                `;

				$("#customer_analysis").html(analysisHtml);
			},
			error: () => {},
		});
	}

	// اقتراح سعر الصرف
	function suggestExchangeRate(currency) {
		if (currency === "AED") {
			const $exchangeRate = $("#exchange_rate");
			$exchangeRate.val("1.00");
			return;
		}

		$.ajax({
			url: `/ai/exchange-rate/${currency}`,
			method: "GET",
			success: (suggestion) => {
				const $exchangeRate = $("#exchange_rate");
				$exchangeRate.val(suggestion.suggested_rate.toFixed(6));

				const sourceInfo = `
                    <small class="text-muted d-block mt-1">
                        <i class="fas fa-info-circle"></i> ${esc(suggestion.source)}
                        ${suggestion.count > 0 ? `(بناءً على ${suggestion.count} معاملات)` : ""}
                    </small>
                `;

				$exchangeRate.parent().find("small").remove();
				$exchangeRate.after(sourceInfo);
			},
		});
	}

	// البحث في الأسواق العالمية
	function searchGlobalMarket(productId, lineIndex) {
		if (!productId) return;

		$.ajax({
			url: `/ai/search-market-price/${productId}`,
			method: "GET",
			success: (result) => {
				if (result.found && result.suggested_price_aed) {
					const marketInfo = `
                        <div class="alert alert-success alert-sm mt-2">
                            <strong>💰 سعر السوق العالمي:</strong><br>
                            <span class="badge badge-primary">${result.average_price_usd} USD</span>
                            <span class="badge badge-info">${result.suggested_price_aed.toFixed(2)} AED</span><br>
                            <small>${esc(result.notes || "")}</small>
                            ${result.markets ? `<br><small>الأسواق: ${result.markets.map(esc).join(", ")}</small>` : ""}
                            <button type="button" class="btn btn-xs btn-success mt-1" onclick="applyMarketPrice(${lineIndex}, ${result.suggested_price_aed})">
                                تطبيق السعر
                            </button>
                        </div>
                    `;
					$(`#market_info_${lineIndex}`).html(marketInfo);
				}
			},
			error: () => {},
		});
	}

	// معرفة التوافق
	function findCompatibleVehicles(productId) {
		if (!productId) return;

		$.ajax({
			url: `/ai/find-compatible/${productId}`,
			method: "GET",
			success: (result) => {
				if (result.found && result.vehicles && result.vehicles.length > 0) {
					let vehiclesHtml =
						'<div class="alert alert-info mt-2"><h6><i class="fas fa-car"></i> متوافقة مع:</h6><ul class="mb-0">';

					result.vehicles.slice(0, 5).forEach((v) => {
						vehiclesHtml += `<li><strong>${esc(v.brand)}</strong>: ${v.models.map(esc).join(", ")} (${esc(v.years)})`;
						if (v.engine) vehiclesHtml += ` - ${esc(v.engine)}`;
						vehiclesHtml += "</li>";
					});

					if (result.total_count > 5) {
						vehiclesHtml += `<li class="text-muted">...و ${result.total_count - 5} أخرى</li>`;
					}

					vehiclesHtml += "</ul>";
					if (result.notes)
						vehiclesHtml += `<small class="text-muted">${esc(result.notes)}</small>`;
					vehiclesHtml += "</div>";

					$("#compatible_vehicles").html(vehiclesHtml);
				} else if (result.raw_response) {
					$("#compatible_vehicles").html(
						`<div class="alert alert-info mt-2">${esc(result.raw_response)}</div>`,
					);
				}
			},
			error: () => {},
		});
	}

	// Events
	$(document).on("change", "#customer_id", function () {
		const customerId = $(this).val();
		analyzeCustomer(customerId);

		// إعادة فحص الأسعار لجميع الأسطر
		$(".product-select").each(function (index) {
			const productId = $(this).val();
			if (productId) {
				checkPriceRecommendation(productId, customerId, index);
			}
		});
	});

	$(document).on("change", ".product-select", function () {
		const lineIndex = $(this).data("line-index");
		const productId = $(this).val();
		const customerId = $("#customer_id").val();

		if (productId && customerId) {
			checkPriceRecommendation(productId, customerId, lineIndex);
		}

		if (productId) {
			searchGlobalMarket(productId, lineIndex);
			findCompatibleVehicles(productId);
		}
	});

	$(document).on("change", ".quantity-input", function () {
		const lineIndex = $(this).data("line-index");
		const productId = $(`.product-select[data-line-index="${lineIndex}"]`).val();
		const quantity = parseFloat($(this).val()) || 0;

		if (productId && quantity > 0) {
			checkStockAlert(productId, quantity, lineIndex);
		}
	});

	$(document).on("change", "#currency", function () {
		const currency = $(this).val();
		suggestExchangeRate(currency);
	});

	// Initialize
	const $currency = $("#currency");
	if ($currency.length) {
		const initialCurrency = $currency.val();
		if (initialCurrency && initialCurrency !== "AED") {
			suggestExchangeRate(initialCurrency);
		}
	}
});

// تطبيق السعر الموصى به
function _applyRecommendedPrice(lineIndex, price) {
	const $unitPrice = $(`#unit_price_${lineIndex}`);
	$unitPrice.val(price.toFixed(2));
	$unitPrice.trigger("change");
	$(`.ai-recommendation`).fadeOut();
}

// تطبيق سعر السوق العالمي
function _applyMarketPrice(lineIndex, price) {
	const $unitPrice = $(`#unit_price_${lineIndex}`);
	$unitPrice.val(price.toFixed(2));
	$unitPrice.trigger("change");
	$(`#market_info_${lineIndex}`).fadeOut();
}
