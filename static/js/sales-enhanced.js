/**
 * Sales Module - Enhanced Features
 * تحسينات خاصة بالمبيعات
 */

/* salesLineIndex scoped per file to avoid cross-page collision with purchases */
let salesLineIndex = 0;

let _isSubmitting = false;

function getCsrfToken() {
	const meta = document.querySelector('meta[name="csrf-token"]');
	return meta ? meta.getAttribute("content") : "";
}

/**
 * Add Product Line
 */
function addLine() {
	const html = `
        <div class="product-line mb-3 p-3" id="line_${salesLineIndex}" style="background: #f8f9fa; border-radius: 8px; border-right: 4px solid #667eea;">
            <div class="row">
                <div class="col-md-5">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-box text-primary"></i> المنتج
                        <span class="text-danger">*</span>
                    </label>
                    <select name="lines[${salesLineIndex}][product_id]" class="form-control product-select" required 
                            data-index="${salesLineIndex}" onchange="loadProductPrice(${salesLineIndex})">
                        <option value="">بلا</option>
                    </select>
                    <small class="text-muted">ابحث بالاسم أو رقم القطعة</small>
                </div>
                <div class="col-md-2">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-sort-numeric-up text-info"></i> الكمية
                        <span class="text-danger">*</span>
                    </label>
                    <input type="number" name="lines[${salesLineIndex}][quantity]" class="form-control quantity-input" 
                           placeholder="الكمية" value="1" step="0.01" min="0.01" required 
                           onchange="calculateTotals()" onkeyup="calculateTotals()">
                    <small class="text-muted">عدد الوحدات</small>
                </div>
                <div class="col-md-2">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-money-bill text-success"></i> السعر
                        <span class="text-danger">*</span>
                    </label>
                    <input type="number" name="lines[${salesLineIndex}][unit_price]" class="form-control price-input" 
                           placeholder="السعر" step="0.01" min="0" required 
                           id="price_${salesLineIndex}" onchange="calculateTotals()" onkeyup="calculateTotals()"
                           title="سعر الوحدة بالعملة الأساسية">
                    <small class="text-muted">${window._CURRENCY_SYMBOL || "₪"}/وحدة</small>
                </div>
                <div class="col-md-2">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-percent text-warning"></i> خصم
                    </label>
                    <input type="number" name="lines[${salesLineIndex}][discount_percent]" class="form-control discount-input" 
                           placeholder="خصم%" value="0" step="0.01" min="0" max="100" 
                           onchange="calculateTotals()" onkeyup="calculateTotals()">
                    <small class="text-muted">نسبة الخصم %</small>
                </div>
                <div class="col-md-2 text-center" id="serial_btn_container_${salesLineIndex}" style="display:none;">
                    <label class="font-weight-bold mb-1">&nbsp;</label>
                    <button type="button" class="btn btn-warning btn-sm btn-block" id="serial_btn_${salesLineIndex}" 
                            onclick="triggerSerialModal(${salesLineIndex})">
                        <i class="fas fa-fingerprint"></i> سيريال
                    </button>
                    <small class="text-muted">مطلوب إدخال السيريال</small>
                </div>
                <div class="col-md-1">
                    <label class="font-weight-bold mb-1">&nbsp;</label>
                    <button type="button" class="btn btn-danger btn-sm btn-block" onclick="removeLine(${salesLineIndex})" title="حذف الصنف">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="row mt-2" id="line_info_${salesLineIndex}" style="display:none;">
                <div class="col-12">
                    <small class="text-muted">
                        <i class="fas fa-box mr-1"></i>المخزون: <span id="stock_${salesLineIndex}">-</span> |
                        <i class="fas fa-dollar-sign mr-1"></i>التكلفة: <span id="cost_${salesLineIndex}">-</span>
                    </small>
                </div>
            </div>
            <div class="row mt-2">
                <div class="col-md-3">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-shield-alt text-success"></i> بداية الضمان
                        <small class="text-muted">(اختياري)</small>
                    </label>
                    <input type="date" name="lines[${salesLineIndex}][warranty_start_date]" class="form-control form-control-sm"
                           title="يبقى فارغاً للاشتقاق التلقائي من مدة ضمان المنتج">
                </div>
                <div class="col-md-3">
                    <label class="font-weight-bold mb-1">
                        <i class="fas fa-calendar-times text-danger"></i> نهاية الضمان
                        <small class="text-muted">(اختياري)</small>
                    </label>
                    <input type="date" name="lines[${salesLineIndex}][warranty_end_date]" class="form-control form-control-sm"
                           title="يبقى فارغاً للاشتقاق التلقائي من مدة ضمان المنتج">
                </div>
            </div>
        </div>
    `;

	$("#linesContainer").append(html);

	const newSelect = $(`select[name="lines[${salesLineIndex}][product_id]"]`);

	// استخدام الفلتر الذكي الموحد
	if (window.SmartSelectors) {
		window.SmartSelectors.initProducts(newSelect[0]);
	} else {
		// Fallback: استخدام API موحد
		newSelect.select2({
			ajax: {
				url: "/api/search",
				dataType: "json",
				delay: 250,
				data: (params) => ({
					q: params.term || "",
					type: "products",
					page: params.page || 1,
				}),
				processResults: (data) => ({
					results: (data.results || []).map((p) => ({
						id: p.id,
						text: p.name || p.text,
						price: p.default_price || p.regular_price || p.unit_price || 0,
						stock: p.current_stock || 0,
						cost: p.cost_price || 0,
						unit: p.unit || "قطعة",
						sku: p.sku,
					})),
					pagination: { more: data.has_more || false },
				}),
			},
			language: "ar",
			dir: "rtl",
			placeholder: "ابحث عن منتج...",
			minimumInputLength: 0,
			width: "100%",
		});
	}

	newSelect.on("select2:select", function (e) {
		// تحميل السعر والمخزون عند اختيار منتج
		const selectedData = e.params.data;
		const currentIndex = $(this).data("index");
		const customerId = $("#customer_id").val();

		// Load price based on customer type
		if (customerId && selectedData.id) {
			$.ajax({
				url: "/sales/api/get-price",
				data: {
					product_id: selectedData.id,
					customer_id: customerId,
				},
				success: (response) => {
					const data = response?.data ? response.data : response;
					if (data.price) {
						_applyBasePrice(currentIndex, data.price);
					}
					if (data.current_stock !== undefined) {
						$(`#stock_${currentIndex}`).text(`${data.current_stock} ${data.unit || ""}`);
						$(`#line_info_${currentIndex}`).show();

						if (data.current_stock < 1) {
							$(`#stock_${currentIndex}`).addClass("text-danger font-weight-bold");
							if (typeof azad !== "undefined") {
								azad.showWarning("⚠️ تنبيه: المخزون منخفض للمنتج");
							}
						}
					}
					if (data.cost_price) {
						$(`#cost_${currentIndex}`).text(
							`${parseFloat(data.cost_price).toFixed(2)} ${window._CURRENCY_SYMBOL || "₪"}`,
						);
					}
					void calculateTotals();
				},
				error: () => {
					// Fallback to selected data
					if (selectedData.price) {
						_applyBasePrice(currentIndex, selectedData.price);
					}
					void calculateTotals();
				},
			});
		} else {
			// Use default price from search result
			if (selectedData.price) {
				_applyBasePrice(currentIndex, selectedData.price);
			}
		}

		if (selectedData.stock !== undefined) {
			$(`#stock_${currentIndex}`).text(`${selectedData.stock} ${selectedData.unit || ""}`);
			$(`#line_info_${currentIndex}`).show();
		}

		if (selectedData.cost) {
			$(`#cost_${currentIndex}`).text(
				`${parseFloat(selectedData.cost).toFixed(2)} ${window._CURRENCY_SYMBOL || "₪"}`,
			);
		}

		// حساب الإجماليات
		void calculateTotals();
	});

	salesLineIndex++;
	$("#line_count").val(salesLineIndex);
}

/**
 * Store a base-currency price on a line and render it converted to the
 * currently selected currency. Keeps `data("base-price")` in sync so
 * updateLinePrices() can re-derive prices when the exchange rate changes.
 */
function _applyBasePrice(index, basePrice) {
	const numericBase = parseFloat(basePrice);
	if (!Number.isFinite(numericBase)) return;
	const $priceInput = $(`#price_${index}`);
	$priceInput.data("base-price", numericBase);
	const rate = parseFloat($("#exchange_rate").val()) || 1;
	const currency = $("#currency").val();
	let finalPrice = numericBase;
	if (currency !== (window._FX_FALLBACK_BASE || "AED") && rate > 0) {
		finalPrice = numericBase / rate;
	}
	$priceInput.val(finalPrice.toFixed(2));
}

/**
 * Remove Product Line
 */
function _removeLine(index) {
	$(`#line_${index}`).remove();
	_serialStore.delete(index);
	if (_serialModalLine === index) _serialModalLine = null;
	void calculateTotals();
}

/**
 * Load Product Price based on Customer Type
 */
function _loadProductPrice(index) {
	const customerId = $("#customer_id").val();
	const productId = $(`select[name="lines[${index}][product_id]"]`).val();

	if (!customerId || !productId) {
		return;
	}

	azad.showLoading();

	$.ajax({
		url: "/sales/api/get-price",
		data: {
			product_id: productId,
			customer_id: customerId,
		},
		success: (response) => {
			const data = response?.data ? response.data : response;
			// Store base price in base currency
			$(`#price_${index}`).data("base-price", data.price);

			// Calculate price based on current currency
			const rate = parseFloat($("#exchange_rate").val()) || 1;
			const currency = $("#currency").val();

			let finalPrice = data.price;
			if (currency !== (window._FX_FALLBACK_BASE || "AED") && rate > 0) {
				finalPrice = data.price / rate;
			}

			$(`#price_${index}`).val(finalPrice.toFixed(2));

			if (data.current_stock !== undefined) {
				$(`#stock_${index}`).text(`${data.current_stock} ${data.unit || ""}`);

				if (data.current_stock < 1) {
					$(`#stock_${index}`).addClass("text-danger font-weight-bold");
					azad.showError(`⚠️ تنبيه: المخزون منخفض للمنتج`);
				}
			}

			if (data.cost_price && data.cost_price > 0) {
				$(`#cost_${index}`).text(`${data.cost_price.toFixed(2)} ${window._CURRENCY_SYMBOL || "₪"}`);
			}

			// Check Serial Number Requirement (Outside cost check, always check product data)
			if (data.has_serial_number) {
				$(`#serial_btn_container_${index}`).show();
				$(`#serial_btn_${index}`).data("product-name", data.name);
				$(`#serial_btn_${index}`).data("needed", true);

				// Adjust column width to fit button
				$(`#serial_btn_container_${index}`).prev().removeClass("col-md-2").addClass("col-md-1"); // Discount
				// $(`#serial_btn_container_${index}`).prev().prev().removeClass('col-md-2').addClass('col-md-2'); // Price
			} else {
				$(`#serial_btn_container_${index}`).hide();
				$(`#serial_btn_${index}`).data("needed", false);
				$(`#serial_btn_container_${index}`).prev().removeClass("col-md-1").addClass("col-md-2"); // Restore Discount
			}

			$(`#line_info_${index}`).show();

			void calculateTotals();
			azad.hideLoading();
		},
		error: () => {
			azad.hideLoading();
			azad.showError("فشل تحميل السعر");
		},
	});
}

/**
 * Serial Number Entry (P2 fix)
 * Serial-required products collect their numbers in the #serialNumberModal
 * present on sales/create.html and write them back as hidden
 * lines[i][serials][] fields consumed by routes/sales.py. Previously this
 * feature was dead code: openSerialModal was referenced but never defined.
 */
const _serialStore = new Map();
let _serialModalLine = null;

function _serialQtyNeeded(lineIndex) {
	return parseInt($(`input[name="lines[${lineIndex}][quantity]"]`).val() || "0", 10) || 0;
}

function _serialHiddenInputs(lineIndex) {
	return $(`#line_${lineIndex}`).find(`input[name="lines[${lineIndex}][serials][]"]`);
}

function _serialSyncFromHidden(lineIndex) {
	const existing = [];
	_serialHiddenInputs(lineIndex).each(function () {
		const value = $(this).val().trim();
		if (value) existing.push(value);
	});
	_serialStore.set(lineIndex, existing);
}

function _serialRenderList() {
	if (_serialModalLine === null) return;
	const serials = _serialStore.get(_serialModalLine) || [];
	const list = $("#serial_list");
	list.empty();
	serials.forEach((sn) => {
		const removeBtn = $("<button></button>")
			.attr("type", "button")
			.addClass("btn btn-sm btn-link text-danger")
			.text("×")
			.on("click", () => _serialRemove(sn));
		list.append(
			$("<li></li>")
				.addClass("list-group-item d-flex justify-content-between align-items-center")
				.append($("<span></span>").text(sn))
				.append(removeBtn),
		);
	});
	$("#serial_count").text(serials.length);
	const needed = _serialQtyNeeded(_serialModalLine);
	$("#save_serials_btn").prop("disabled", needed === 0 || serials.length !== needed);
	$("#serial_input").val("").focus();
}

function _serialAdd() {
	if (_serialModalLine === null) return;
	const input = $("#serial_input");
	const value = input.val().trim();
	if (!value) return;
	const serials = _serialStore.get(_serialModalLine) || [];
	if (serials.includes(value)) {
		azad.showError("⚠️ هذا الرقم التسلسلي مُدخل مسبقاً");
		return;
	}
	serials.push(value);
	_serialStore.set(_serialModalLine, serials);
	_serialRenderList();
}

function _serialGenerate() {
	if (_serialModalLine === null) return;
	const serials = _serialStore.get(_serialModalLine) || [];
	const needed = _serialQtyNeeded(_serialModalLine);
	let attempts = 0;
	while (serials.length < needed && attempts < needed * 10) {
		attempts++;
		const datePart = new Date().toISOString().slice(0, 10).replace(/-/g, "");
		const randomPart = Math.random().toString(36).substring(2, 6).toUpperCase();
		const candidate = `${datePart}-${randomPart}`;
		if (!serials.includes(candidate)) serials.push(candidate);
	}
	_serialStore.set(_serialModalLine, serials);
	_serialRenderList();
}

function _serialRemove(sn) {
	if (_serialModalLine === null) return;
	_serialStore.set(
		_serialModalLine,
		(_serialStore.get(_serialModalLine) || []).filter((s) => s !== sn),
	);
	_serialRenderList();
}

function _serialPrint() {
	if (_serialModalLine === null) return;
	const serials = _serialStore.get(_serialModalLine) || [];
	if (serials.length === 0) return;
	const printWindow = window.open("", "_blank", "width=400,height=600");
	printWindow.document.open();
	printWindow.document.write("<html><head><title>طباعة الأرقام التسلسلية</title>");
	printWindow.document.write(
		"<style>body{font-family:Arial;padding:20px}.serial{border:1px solid #000;padding:8px;margin:4px 0;text-align:center;font-size:18px;letter-spacing:2px}</style>",
	);
	printWindow.document.write("</head><body>");
	printWindow.document.write('<h2 style="text-align:center">الأرقام التسلسلية</h2>');
	serials.forEach((s) => {
		const safe = String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
		printWindow.document.write(`<div class="serial">${safe}</div>`);
	});
	printWindow.document.write("</body></html>");
	printWindow.document.close();
	printWindow.print();
}

function _serialSave() {
	if (_serialModalLine === null) return;
	const lineIndex = _serialModalLine;
	const serials = _serialStore.get(lineIndex) || [];
	_serialHiddenInputs(lineIndex).remove();
	const container = $(`#line_${lineIndex}`);
	serials.forEach((sn) => {
		container.append(
			$('<input type="hidden">').attr("name", `lines[${lineIndex}][serials][]`).val(sn),
		);
	});
	$("#serialNumberModal").modal("hide");
}

/**
 * Trigger Serial Modal
 */
function _triggerSerialModal(salesLineIndex) {
	const btn = $(`#serial_btn_${salesLineIndex}`);
	if (!btn.data("needed")) return;

	const productName = btn.data("product-name");
	_serialModalLine = salesLineIndex;
	_serialSyncFromHidden(salesLineIndex);
	$("#serial_product_name").text(productName || "");
	$("#serial_quantity_needed").text(String(_serialQtyNeeded(salesLineIndex)));
	_serialRenderList();
	$("#serialNumberModal").modal("show");
}

/**
 * Update all line prices based on exchange rate
 */
function updateLinePrices() {
	const $exchangeRate = $("#exchange_rate");
	const $currency = $("#currency");
	const rate = parseFloat($exchangeRate.val()) || 1;
	const currency = $currency.val();

	$(".product-line").each(function () {
		const index = $(this).find(".product-select").data("index");
		const $priceInput = $(`#price_${index}`);
		const basePrice = parseFloat($priceInput.data("base-price"));

		if (!Number.isNaN(basePrice)) {
			let finalPrice = basePrice;
			if (currency !== (window._FX_FALLBACK_BASE || "AED") && rate > 0) {
				finalPrice = basePrice / rate;
			}
			$priceInput.val(finalPrice.toFixed(2));
		}
	});

	updateCurrencyLabels();
	void calculateTotals();
}

function updateCurrencyLabels() {
	const $currency = $("#currency");
	const currency = $currency.val();
	$("#discount_currency").text(currency);
	$("#shipping_currency").text(currency);
	$("#total_currency_label").text(currency);
}

/**
 * Calculate All Totals
 */
// حساب الإجماليات - Backend Calculation
let _totalsServerDown = false;

// Warn once per outage episode instead of spamming a toast on every keystroke.
function _clientSideFallback() {
	if (!_totalsServerDown) {
		_totalsServerDown = true;
		azad.showWarning(
			"⚠️ تعذر الاتصال بالخادم — تم حساب الإجماليات محلياً وقد تختلف عن الحساب الرسمي",
		);
	}
	return calculateTotalsClientSide();
}

async function calculateTotals() {
	try {
		// جمع البيانات من الفورم
		const lines = [];
		$('[name^="lines"][name$="[quantity]"]').each(function () {
			const $line = $(this).closest(".product-line");
			const qty = parseFloat($(this).val()) || 0;
			const price = parseFloat($line.find('[name$="[unit_price]"]').val()) || 0;
			const discount = parseFloat($line.find('[name$="[discount_percent]"]').val()) || 0;

			if (qty > 0 || price > 0) {
				lines.push({
					quantity: qty,
					unit_price: price,
					discount_percent: discount,
				});
			}
		});

		const discount_amount = parseFloat($('[name="discount_amount"]').val()) || 0;
		const shipping_cost = parseFloat($('[name="shipping_cost"]').val()) || 0;
		const tax_rate = parseFloat($('[name="tax_rate"]').val()) || 0;

		// إرسال للـ backend
		const response = await fetch("/sales/api/calculate-totals", {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-CSRFToken": getCsrfToken(),
			},
			credentials: "same-origin",
			body: JSON.stringify({
				lines: lines,
				discount_amount: discount_amount,
				shipping_cost: shipping_cost,
				tax_rate: tax_rate,
			}),
		});

		const responseJson = await response.json();
		const result = responseJson?.data ? responseJson.data : responseJson;

		if (responseJson.success) {
			_totalsServerDown = false;
			// تحديث الواجهة
			$("#subtotal").text(azad.formatNumber(result.subtotal));
			$("#total").text(azad.formatNumber(result.total));
			$("#line_count_display").text(result.line_count);

			return {
				subtotal: result.subtotal,
				discount: result.discount,
				shipping: result.shipping,
				tax: result.tax_amount,
				total: result.total,
				lineCount: result.line_count,
			};
		} else {
			// Fallback to client-side calculation
			return _clientSideFallback();
		}
	} catch (_error) {
		// Fallback to client-side calculation
		return _clientSideFallback();
	}
}

// Fallback: حساب محلي في حالة فشل الـ backend
function calculateTotalsClientSide() {
	let subtotal = 0;
	let lineCount = 0;

	$('[name^="lines"][name$="[quantity]"]').each(function () {
		const qty = parseFloat($(this).val()) || 0;
		const price =
			parseFloat($(this).closest(".product-line").find('[name$="[unit_price]"]').val()) || 0;
		const discount =
			parseFloat($(this).closest(".product-line").find('[name$="[discount_percent]"]').val()) || 0;

		if (qty > 0 && price > 0) {
			const lineTotal = qty * price * (1 - discount / 100);
			subtotal += lineTotal;
			lineCount++;
		}
	});

	const discount = parseFloat($('[name="discount_amount"]').val()) || 0;
	const shipping = parseFloat($('[name="shipping_cost"]').val()) || 0;
	const taxRate = parseFloat($('[name="tax_rate"]').val()) || 0;

	const afterDiscount = subtotal - discount + shipping;
	const tax = afterDiscount * (taxRate / 100);
	const total = afterDiscount + tax;

	$("#subtotal").text(azad.formatNumber(subtotal));
	$("#total").text(azad.formatNumber(total));
	$("#line_count_display").text(lineCount);

	return {
		subtotal: subtotal,
		discount: discount,
		shipping: shipping,
		tax: tax,
		total: total,
		lineCount: lineCount,
	};
}

/**
 * Load Exchange Rate when Currency Changes
 * Allows manual editing with audit trail
 */
let serverExchangeRate = null; // Store server rate for comparison

$("#currency").on("change", function () {
	const currency = $(this).val();
	const $rateInput = $("#exchange_rate");

	// Update payment currency display
	$("#payment_currency_display").text(currency);

	if (currency === (window._FX_FALLBACK_BASE || "AED")) {
		$rateInput.val("1.000000");
		$rateInput.data("server-rate", 1);
		serverExchangeRate = 1;
		$rateInput.prop("readonly", false);
		$rateInput.css("background-color", "#e9ecef");
		azad.showInfo(
			`💡 العملة: ${window._CURRENCY_NAME_AR || "درهم"} - الأسعار والمدفوع بالـ${window._CURRENCY_NAME_AR || "درهم"}`,
		);
		return;
	}

	$rateInput.val("...").css("background-color", "#fff8dc");

	$.ajax({
		url: `/api/currency-rate/${currency}/${window._FX_FALLBACK_BASE || "AED"}`,
		success: (data) => {
			if (data.rate) {
				serverExchangeRate = data.rate;
				$rateInput.val(data.rate.toFixed(6));
				$rateInput.data("server-rate", data.rate);
				$rateInput.prop("readonly", false);
				$rateInput.css("background-color", "#d4edda");
				azad.showSuccess(
					`✅ تم جلب سعر الصرف: 1 ${currency} = ${data.rate.toFixed(3)} ${window._FX_FALLBACK_BASE || "AED"}`,
				);
				updateLinePrices();
			} else if (data.manual_input_required) {
				serverExchangeRate = null;
				$rateInput.val("");
				$rateInput.prop("readonly", false);
				$rateInput.css("background-color", "#fff3cd");
				$rateInput.focus();
				azad.showError("⚠️ يرجى إدخال سعر الصرف يدوياً");
			}
		},
		error: () => {
			serverExchangeRate = null;
			$rateInput.val("");
			$rateInput.prop("readonly", false);
			$rateInput.css("background-color", "#f8d7da");
			azad.showError("⚠️ فشل تحميل سعر الصرف - يرجى الإدخال يدوياً");
		},
	});
});

// Audit manual exchange rate changes
$("#exchange_rate").on("change", function () {
	const manualRate = parseFloat($(this).val());
	const serverRate = parseFloat($(this).data("server-rate")) || serverExchangeRate;

	if (!manualRate || manualRate <= 0) {
		azad.showError("⚠️ سعر الصرف يجب أن يكون أكبر من صفر");
		if (serverRate) {
			$(this).val(serverRate.toFixed(6));
		}
		return;
	}

	if (serverRate && manualRate !== serverRate) {
		const diff = (((manualRate - serverRate) / serverRate) * 100).toFixed(2);
		const diffText = diff > 0 ? `+${diff}%` : `${diff}%`;

		if (manualRate < serverRate) {
			// Manual rate is lower than server rate - requires documentation
			$(this).css("background-color", "#f8d7da");
			azad.showWarning(
				`⚠️ تحذير: سعر الصرف المدخل (${manualRate.toFixed(6)}) أقل من سعر السيرفر (${serverRate.toFixed(6)}) بنسبة ${diffText}` +
					`\nسيتم توثيق هذا التغيير في سجل العمليات`,
			);

			// Add hidden field to track manual override
			const $saleForm = $("#saleForm");
			$saleForm.find('input[name="exchange_rate_manual"]').remove();
			$saleForm.append(`
                <input type="hidden" name="exchange_rate_manual" value="true">
                <input type="hidden" name="exchange_rate_server" value="${serverRate}">
                <input type="hidden" name="exchange_rate_difference" value="${diff}">
            `);
		} else if (manualRate > serverRate) {
			$(this).css("background-color", "#d1ecf1");
			azad.showInfo(`ℹ️ سعر الصرف المدخل أعلى من السيرفر بنسبة ${diffText}`);
		} else {
			$(this).css("background-color", "#d4edda");
		}
	} else if (!serverRate) {
		// Manual input without server rate
		$(this).css("background-color", "#fff3cd");
		const $saleForm = $("#saleForm");
		$saleForm.find('input[name="exchange_rate_manual"]').remove();
		$saleForm.append(`<input type="hidden" name="exchange_rate_manual" value="true">`);
	}

	updateLinePrices();
});

/**
 * Handle Payment Method Change - Show Dynamic Fields
 */
$("#payment_method").on("change", function () {
	const method = $(this).val();
	const $container = $("#payment_fields_container");
	const $amountGroup = $("#payment_amount_group");

	// Clear previous fields
	$container.empty();

	if (!method) {
		// No payment method selected (deferred payment)
		$amountGroup.hide();
		return;
	}

	// Show payment amount field
	$amountGroup.show();

	// Load dynamic fields from API
	$.ajax({
		url: `/api/payment-fields/${method}`,
		success: (data) => {
			if (data.fields && data.fields.length > 0) {
				let html = '<hr class="my-3">';
				html += `<h6 class="mb-3">${data.ar_title || "تفاصيل الدفع"}</h6>`;

				data.fields.forEach((field) => {
					const label = field.label_ar || field.label || field.name;
					const required = field.required ? "required" : "";
					const requiredStar = field.required ? " *" : "";

					html += `
                        <div class="form-group">
                            <label class="font-weight-bold">${label}${requiredStar}</label>
                    `;

					if (field.type === "select" && field.options) {
						html += `<select name="${field.name}" class="form-control" ${required}>`;
						html += '<option value="">اختر...</option>';
						field.options.forEach((opt) => {
							html += `<option value="${opt.value}">${opt.label_ar || opt.label_en}</option>`;
						});
						html += "</select>";
					} else {
						html += `
                            <input 
                                type="${field.type || "text"}" 
                                name="${field.name}" 
                                class="form-control" 
                                ${required}
                                placeholder="${label}">
                        `;
					}

					html += "</div>";
				});

				$container.html(html);
			}
		},
		error: () => {
			azad.showError("⚠️ فشل تحميل حقول الدفع");
		},
	});
});

/**
 * Initialize on Document Ready
 */
$(document).ready(() => {
	$("#customer_id").select2({
		placeholder: "ابحث عن زبون...",
		language: "ar",
		dir: "rtl",
		width: "100%",
		ajax: {
			url: "/api/search",
			dataType: "json",
			delay: 250,
			data: (params) => ({
				q: params.term,
				type: "customers",
				page: params.page || 1,
			}),
			processResults: (data) => ({
				results: data.results,
				pagination: {
					more: data.has_more,
				},
			}),
			cache: true,
		},
		minimumInputLength: 0,
		templateResult: (customer) => {
			if (customer.loading) return customer.text;
			return $(`<span>${customer.text}</span>`);
		},
		templateSelection: (customer) => customer.text,
	});

	addLine();

	$('[name="discount_amount"], [name="shipping_cost"], [name="tax_rate"]').on(
		"change keyup",
		() => {
			void calculateTotals();
		},
	);

	$("#saleForm").on("submit", async function (e) {
		e.preventDefault();
		if (_isSubmitting) return false;
		_isSubmitting = true;
		const submitBtn = this.querySelector('[type="submit"]');
		if (submitBtn) {
			submitBtn.disabled = true;
			submitBtn.classList.add("btn-loading");
		}
		const release = () => {
			_isSubmitting = false;
			if (submitBtn) {
				submitBtn.disabled = false;
				submitBtn.classList.remove("btn-loading");
			}
		};
		const totals = await calculateTotals();

		if (totals.lineCount === 0) {
			release();
			azad.showError("⚠️ يجب إضافة منتج واحد على الأقل");
			return false;
		}

		// Don't block if total is 0 - could be all free items
		if (totals.total < 0) {
			release();
			azad.showError("⚠️ الإجمالي لا يمكن أن يكون سالب");
			return false;
		}

		if (!$("#customer_id").val()) {
			release();
			azad.showError("⚠️ يجب اختيار زبون");
			return false;
		}

		azad.showLoading();
		this.submit();
	});

	$(document).on("click", '[data-action="add-line"]', () => {
		addLine();
	});

	// Wire the serial entry modal (template: sales/create.html).
	if (document.getElementById("serialNumberModal")) {
		$("#add_serial_btn").on("click", _serialAdd);
		$("#generate_serial_btn").on("click", _serialGenerate);
		$("#print_serials_btn").on("click", _serialPrint);
		$("#save_serials_btn").on("click", _serialSave);
	}
});

// Expose the handlers referenced by inline onclick/onchange attributes in the
// line markup generated by addLine() (they are intentionally file-private).
window.loadProductPrice = _loadProductPrice;
window.triggerSerialModal = _triggerSerialModal;
window.removeLine = _removeLine;
