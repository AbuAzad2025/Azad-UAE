/**
 * 💳 Payment Fields Manager - Dynamic Payment Method Fields
 * إدارة ديناميكية لحقول طرق الدفع في كل الوحدات
 */

(($) => {
	// =====================================
	// تعريف حقول كل طريقة دفع
	// =====================================
	const PAYMENT_METHODS = {
		cash: {
			title_ar: "دفع نقدي",
			title_en: "Cash Payment",
			icon: "fas fa-money-bill-wave",
			color: "success",
			fields: [],
		},

		card: {
			title_ar: "دفع ببطاقة",
			title_en: "Card Payment",
			icon: "fas fa-credit-card",
			color: "primary",
			fields: [
				{
					name: "card_last4",
					type: "text",
					label_ar: "آخر 4 أرقام البطاقة",
					label_en: "Card Last 4 Digits",
					required: false,
					maxlength: 4,
					pattern: "[0-9]{4}",
					placeholder: "1234",
				},
				{
					name: "card_type",
					type: "select",
					label_ar: "نوع البطاقة",
					label_en: "Card Type",
					required: false,
					options: [
						{ value: "", label: "اختر..." },
						{ value: "visa", label: "Visa" },
						{ value: "mastercard", label: "Mastercard" },
						{ value: "amex", label: "American Express" },
						{ value: "other", label: "أخرى" },
					],
				},
				{
					name: "reference_number",
					type: "text",
					label_ar: "رقم المعاملة",
					label_en: "Transaction Number",
					required: false,
					placeholder: "REF-123456",
				},
			],
		},

		bank_transfer: {
			title_ar: "تحويل بنكي",
			title_en: "Bank Transfer",
			icon: "fas fa-university",
			color: "info",
			fields: [
				{
					name: "reference_number",
					type: "text",
					label_ar: "رقم الحوالة",
					label_en: "Transfer Reference",
					required: true,
					placeholder: "TRF-123456",
				},
				{
					name: "bank_name",
					type: "text",
					label_ar: "اسم البنك",
					label_en: "Bank Name",
					required: false,
					placeholder: "Emirates NBD",
				},
				{
					name: "transfer_date",
					type: "date",
					label_ar: "تاريخ التحويل",
					label_en: "Transfer Date",
					required: false,
				},
			],
		},

		cheque: {
			title_ar: "دفع بشيك",
			title_en: "Cheque Payment",
			icon: "fas fa-file-invoice",
			color: "warning",
			fields: [
				{
					name: "cheque_number",
					type: "text",
					label_ar: "رقم الشيك",
					label_en: "Cheque Number",
					required: true,
					placeholder: "CHQ-123456",
				},
				{
					name: "cheque_date",
					type: "date",
					label_ar: "تاريخ الاستحقاق",
					label_en: "Due Date",
					required: true,
				},
				{
					name: "bank_name",
					type: "text",
					label_ar: "اسم البنك",
					label_en: "Bank Name",
					required: true,
					placeholder: "Emirates NBD",
				},
				{
					name: "cheque_status",
					type: "select",
					label_ar: "حالة الشيك",
					label_en: "Cheque Status",
					required: false,
					options: [
						{ value: "pending", label: "معلق" },
						{ value: "cleared", label: "تم الصرف" },
						{ value: "bounced", label: "مرتد" },
					],
				},
			],
		},

		e_wallet: {
			title_ar: "محفظة إلكترونية",
			title_en: "E-Wallet",
			icon: "fas fa-wallet",
			color: "purple",
			fields: [
				{
					name: "wallet_provider",
					type: "select",
					label_ar: "مزود المحفظة",
					label_en: "Wallet Provider",
					required: true,
					options: [
						{ value: "", label: "اختر..." },
						{ value: "apple_pay", label: "Apple Pay" },
						{ value: "google_pay", label: "Google Pay" },
						{ value: "samsung_pay", label: "Samsung Pay" },
						{ value: "paypal", label: "PayPal" },
						{ value: "other", label: "أخرى" },
					],
				},
				{
					name: "reference_number",
					type: "text",
					label_ar: "رقم المعاملة",
					label_en: "Transaction ID",
					required: true,
					placeholder: "TXN-123456",
				},
				{
					name: "wallet_phone",
					type: "text",
					label_ar: "رقم المحفظة",
					label_en: "Wallet Phone",
					required: false,
					placeholder: "+971-xxx-xxx-xxx",
				},
			],
		},

		credit: {
			title_ar: "آجل (على الحساب)",
			title_en: "Credit",
			icon: "fas fa-calendar-check",
			color: "danger",
			fields: [
				{
					name: "credit_days",
					type: "number",
					label_ar: "مدة الائتمان (أيام)",
					label_en: "Credit Days",
					required: false,
					min: 1,
					value: 30,
				},
				{
					name: "due_date",
					type: "date",
					label_ar: "تاريخ الاستحقاق",
					label_en: "Due Date",
					required: false,
				},
			],
		},
	};

	// =====================================
	// إنشاء حقول ديناميكية
	// =====================================
	function renderPaymentFields(method, containerSelector, fieldPrefix = "") {
		$(containerSelector).empty();

		if (!method || method === "" || !PAYMENT_METHODS[method]) {
			return;
		}

		const methodConfig = PAYMENT_METHODS[method];
		const fields = methodConfig.fields;

		if (fields.length === 0) {
			$container.html(`
        <div class="alert alert-success">
          <i class="${methodConfig.icon} mr-2"></i>
          <strong>${methodConfig.title_ar}</strong> - لا توجد حقول إضافية مطلوبة
        </div>
      `);
			return;
		}

		let html = `
      <div class="card border-${methodConfig.color} mb-3">
        <div class="card-header bg-${methodConfig.color} text-white">
          <i class="${methodConfig.icon} mr-2"></i>
          <strong>${methodConfig.title_ar}</strong>
        </div>
        <div class="card-body">
          <div class="row">
    `;

		fields.forEach((field) => {
			const fieldName = fieldPrefix
				? `${fieldPrefix}_${field.name}`
				: field.name;
			const requiredAttr = field.required ? "required" : "";
			const requiredLabel = field.required
				? '<span class="text-danger">*</span>'
				: "";

			html += '<div class="col-md-6"><div class="form-group">';
			html += `<label>${field.label_ar} ${requiredLabel}</label>`;

			if (field.type === "select") {
				html += `<select name="${fieldName}" class="form-control" ${requiredAttr}>`;
				field.options.forEach((opt) => {
					html += `<option value="${opt.value}">${opt.label}</option>`;
				});
				html += "</select>";
			} else if (field.type === "textarea") {
				html += `<textarea name="${fieldName}" class="form-control" rows="2" 
                  placeholder="${field.placeholder || ""}" ${requiredAttr}></textarea>`;
			} else {
				const attrs = [];
				if (field.maxlength) attrs.push(`maxlength="${field.maxlength}"`);
				if (field.pattern) attrs.push(`pattern="${field.pattern}"`);
				if (field.min) attrs.push(`min="${field.min}"`);
				if (field.max) attrs.push(`max="${field.max}"`);
				if (field.value) attrs.push(`value="${field.value}"`);

				html += `<input type="${field.type}" name="${fieldName}" class="form-control" 
                  placeholder="${field.placeholder || ""}" ${attrs.join(" ")} ${requiredAttr}>`;
			}

			html += "</div></div>";
		});

		html += `
          </div>
        </div>
      </div>
    `;

		$container.html(html);
	}

	// =====================================
	// جمع بيانات الحقول
	// =====================================
	function collectPaymentData(method, containerSelector, fieldPrefix = "") {
		if (!method || !PAYMENT_METHODS[method]) {
			return {};
		}

		const data = { payment_method: method };
		const fields = PAYMENT_METHODS[method].fields;

		fields.forEach((field) => {
			const fieldName = fieldPrefix
				? `${fieldPrefix}_${field.name}`
				: field.name;
			const $field = $(`[name="${fieldName}"]`);
			if ($field.length) {
				data[field.name] = $field.val();
			}
		});

		return data;
	}

	// =====================================
	// تعبئة الحقول من البيانات
	// =====================================
	function populatePaymentFields(
		method,
		data,
		containerSelector,
		fieldPrefix = "",
	) {
		if (!method || !data || !PAYMENT_METHODS[method]) {
			return;
		}

		const fields = PAYMENT_METHODS[method].fields;

		fields.forEach((field) => {
			const fieldName = fieldPrefix
				? `${fieldPrefix}_${field.name}`
				: field.name;
			const $field = $(`[name="${fieldName}"]`);
			if ($field.length && data[field.name]) {
				$field.val(data[field.name]);
			}
		});
	}

	// =====================================
	// API عامة
	// =====================================
	// noinspection JSUnusedGlobalSymbols
	window.PaymentFieldsManager = {
		methods: PAYMENT_METHODS,
		render: renderPaymentFields,
		collect: collectPaymentData,
		populate: populatePaymentFields,

		// تهيئة تلقائية لعنصر select
		initSelector: (selectSelector, containerSelector, fieldPrefix = "") => {
			const $select = $(selectSelector);
			const $container = $(containerSelector);

			// رسم الحقول عند التغيير
			$select.on("change", function () {
				const method = $(this).val();
				renderPaymentFields(method, containerSelector, fieldPrefix);
			});

			// رسم الحقول الأولية إذا كانت هناك قيمة
			const initialMethod = $select.val();
			if (initialMethod) {
				renderPaymentFields(initialMethod, containerSelector, fieldPrefix);
			}
		},

		// الحصول على معلومات طريقة دفع
		getMethodInfo: (method) => PAYMENT_METHODS[method] || null,
	};
})(jQuery);
