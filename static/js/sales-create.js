/**
 * Sales Create Form - Serial Number Management
 * إدارة الأرقام التسلسلية للمنتجات في فاتورة المبيعات
 */

$(document).ready(() => {
	// Initialize serial number inputs
	const $serialsContainer = $("#serials_input_container");

	// Generate serial number
	function generateSerialNumber(productId = "") {
		const datePart = new Date().toISOString().slice(0, 10).replace(/-/g, "");
		const randomPart = Math.random().toString(36).substring(2, 6).toUpperCase();
		const productPart = productId ? `-${productId}` : "";
		return `${datePart}-${randomPart}${productPart}`;
	}

	// Add serial input row
	function addSerialInput(lineIndex, count = 1) {
		for (let i = 0; i < count; i++) {
			const serialIndex = Date.now() + i;
			const html = `
        <div class="input-group mb-2 serial-row" data-serial-index="${serialIndex}">
          <input type="text" name="serials[${lineIndex}][${serialIndex}]" class="form-control form-control-sm serial-input"
                 placeholder="أدخل الرقم التسلسلي" required
                 aria-label="الرقم التسلسلي للصنف">
          <div class="input-group-append">
            <button type="button" class="btn btn-success btn-sm generate-serial-btn" title="توليد تلقائي">
              <i class="fas fa-magic"></i>
            </button>
            <button type="button" class="btn btn-danger btn-sm remove-serial-btn" title="حذف">
              <i class="fas fa-times"></i>
            </button>
          </div>
        </div>
      `;
			$serialsContainer.append(html);
		}
		updateSerialsCount();
	}

	// Generate and insert serial for quantity
	function generateSerials(lineIndex, productId, qty) {
		$serialsContainer.empty();
		const count = parseInt(qty) || 1;
		addSerialInput(lineIndex, count);
	}

	// Update serials count
	function updateSerialsCount() {
		$("#serials_count").text($(".serial-row").length);
	}

	// Event delegation: generate single serial
	$serialsContainer.on("click", ".generate-serial-btn", function () {
		const $row = $(this).closest(".serial-row");
		const productId = $("#product_id").val() || "";
		$row.find(".serial-input").val(generateSerialNumber(productId));
	});

	// Event delegation: remove row
	$serialsContainer.on("click", ".remove-serial-btn", function () {
		const $row = $(this).closest(".serial-row");
		if ($(".serial-row").length > 1) {
			$row.remove();
		} else {
			$row.find(".serial-input").val("");
		}
		updateSerialsCount();
	});

	// Trigger serial modal
	$("#add_serial_btn").on("click", () => {
		const lineIndex = $("#serial_line_index").val();
		const productId = $("#product_id").val();
		const productName = $("#product_name").val();
		const quantity = $("#quantity").val();

		if (!productId) {
			alert("يرجى اختيار منتج أولاً");
			return;
		}

		generateSerials(lineIndex, productId, quantity);
		$("#serialModal").modal("show");
	});

	$("#generate_serial_btn").on("click", () => {
		const productId = $("#product_id").val() || "";
		const count = parseInt($("#serials_count").text()) || 1;
		$(".serial-input").each(function (index) {
			if (!$(this).val()) {
				$(this).val(generateSerialNumber(productId));
			}
		});
	});

	$("#print_serials_btn").on("click", () => {
		const serials = [];
		$(".serial-input").each(function () {
			const val = $(this).val().trim();
			if (val) serials.push(val);
		});
		if (serials.length === 0) {
			alert("لا توجد أرقام تسلسلية للطباعة");
			return;
		}
		const printWindow = window.open("", "_blank", "width=400,height=600");
		var _printDoc = printWindow.document;
		_printDoc.open();
		_printDoc.write("<html><head><title>طباعة الأرقام التسلسلية</title>");
		_printDoc.write(
			"<style>body{font-family:Arial;padding:20px}.serial{border:1px solid #000;padding:8px;margin:4px 0;text-align:center;font-size:18px;letter-spacing:2px}</style>",
		);
		_printDoc.write("</head><body>");
		_printDoc.write('<h2 style="text-align:center">الأرقام التسلسلية</h2>');
		serials.forEach((s) => {
			_printDoc.write('<div class="serial">' + s + "</div>");
		});
		_printDoc.write("</body></html>");
		_printDoc.close();
		printWindow.document.close();
		printWindow.print();
	});

	$("#save_serials_btn").on("click", () => {
		$("#serialModal").modal("hide");
	});
});
