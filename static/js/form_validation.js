(() => {
	const MSG = {
		required: "هذا الحقل مطلوب",
		email: "بريد إلكتروني غير صالح",
		minlength: "الحد الأدنى {0} أحرف",
		maxlength: "الحد الأقصى {0} حرف",
		pattern: "قيمة غير صالحة",
		min: "الحد الأدنى {0}",
		max: "الحد الأقصى {0}",
		number: "قيمة رقمية غير صالحة",
		digits: "أرقام فقط",
		equalTo: "القيمتان غير متطابقتين",
		phone: "رقم هاتف غير صالح",
		date: "تاريخ غير صالح",
		url: "رابط غير صالح",
		fileSize: "حجم الملف يتجاوز الحد المسموح",
		fileType: "نوع الملف غير مسموح به",
	};

	const PHONE_RE = /^[+]?[0-9\s-]{8,20}$/;
	const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
	const URL_RE = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*\/?$/;

	function showError(input, msg) {
		input.classList.add("is-invalid");
		input.setAttribute("aria-invalid", "true");

		let fb = input.parentElement.querySelector(".invalid-feedback");
		if (!fb) {
			fb = document.createElement("div");
			fb.className = "invalid-feedback";
			input.parentElement.appendChild(fb);
		}
		fb.textContent = msg;
		fb.id = fb.id || `error-${input.name || Math.random().toString(36).substr(2, 9)}`;
		input.setAttribute("aria-describedby", fb.id);
	}

	function clearError(input) {
		input.classList.remove("is-invalid");
		input.removeAttribute("aria-invalid");
		const fb = input.parentElement.querySelector(".invalid-feedback");
		if (fb) {
			fb.textContent = "";
			fb.style.display = "none";
		}
	}

	function validateField(input) {
		const val = input.value.trim();
		const type = input.type;
		const name = input.name;
		let err = null;

		// Required check
		if (input.required && !val) {
			err = MSG.required;
		} else if (val) {
			// Type-specific validation
			switch (type) {
				case "email":
					if (!EMAIL_RE.test(val)) err = MSG.email;
					break;
				case "url":
					if (!URL_RE.test(val)) err = MSG.url;
					break;
				case "number":
					if (Number.isNaN(Number(val))) err = MSG.number;
					break;
				case "date":
					if (Number.isNaN(Date.parse(val))) err = MSG.date;
					break;
			}

			// Name-based validation
			if (
				!err &&
				name &&
				(name.includes("phone") || name.includes("mobile") || name.includes("tel"))
			) {
				if (!PHONE_RE.test(val)) err = MSG.phone;
			}

			// Length validation
			if (!err && input.minLength > 0 && val.length < input.minLength) {
				err = MSG.minlength.replace("{0}", input.minLength);
			}
			if (!err && input.maxLength > 0 && val.length > input.maxLength) {
				err = MSG.maxlength.replace("{0}", input.maxLength);
			}

			// Pattern validation
			if (!err && input.pattern) {
				const re = new RegExp(input.pattern);
				if (!re.test(val)) err = MSG.pattern;
			}

			// Min/Max value
			if (!err && input.min && Number(val) < Number(input.min)) {
				err = MSG.min.replace("{0}", input.min);
			}
			if (!err && input.max && Number(val) > Number(input.max)) {
				err = MSG.max.replace("{0}", input.max);
			}

			// Digits only
			if (!err && input.dataset.digits === "true" && !/^\d+$/.test(val)) {
				err = MSG.digits;
			}

			// File validation
			if (!err && type === "file" && input.files.length > 0) {
				const file = input.files[0];
				const maxSize = parseInt(input.dataset.maxSize || "0", 10);
				const acceptTypes = (input.accept || "")
					.split(",")
					.map((t) => t.trim())
					.filter(Boolean);

				if (maxSize > 0 && file.size > maxSize) {
					err = MSG.fileSize;
				}
				if (!err && acceptTypes.length > 0) {
					const ext = file.name.split(".").pop().toLowerCase();
					const mimeOk = acceptTypes.some((t) => file.type.match(t.replace("*", ".*")));
					const extOk = acceptTypes.some((t) => t.includes(ext));
					if (!mimeOk && !extOk) err = MSG.fileType;
				}
			}
		}

		// Equal-to validation
		if (!err && input.dataset.equalTo) {
			const target = document.querySelector(input.dataset.equalTo);
			if (target && val !== target.value.trim()) {
				err = MSG.equalTo;
			}
		}

		if (err) showError(input, err);
		else clearError(input);
		return !err;
	}

	function validateForm(form) {
		let ok = true;
		const inputs = form.querySelectorAll("input, select, textarea");
		let firstInvalid = null;

		inputs.forEach((input) => {
			if (!validateField(input)) {
				ok = false;
				if (!firstInvalid) firstInvalid = input;
			}
		});

		if (firstInvalid) {
			firstInvalid.focus();
			if (typeof firstInvalid.scrollIntoView === "function") {
				firstInvalid.scrollIntoView({ behavior: "smooth", block: "center" });
			}
		}

		return ok;
	}

	function init() {
		document.querySelectorAll("form.needs-validation").forEach((form) => {
			form.setAttribute("novalidate", "");
			form.setAttribute("aria-label", form.getAttribute("aria-label") || "نموذج");

			form.addEventListener("submit", (e) => {
				if (!validateForm(form)) {
					e.preventDefault();
					e.stopPropagation();
					// Shake animation on invalid form
					form.classList.add("az-shake");
					setTimeout(() => form.classList.remove("az-shake"), 500);
				}
			});

			const inputs = form.querySelectorAll("input, select, textarea");
			inputs.forEach((input) => {
				// Validate on blur
				input.addEventListener("blur", () => validateField(input));

				// Real-time validation (only if already invalid)
				input.addEventListener("input", () => {
					if (input.classList.contains("is-invalid")) validateField(input);
				});

				// Validate on change
				input.addEventListener("change", () => validateField(input));
			});
		});
	}

	// CSS for shake animation
	if (!document.getElementById("az-form-validation-styles")) {
		const style = document.createElement("style");
		style.id = "az-form-validation-styles";
		style.textContent = `
      @keyframes az-shake {
        0%, 100% { transform: translateX(0); }
        20% { transform: translateX(-5px); }
        40% { transform: translateX(5px); }
        60% { transform: translateX(-3px); }
        80% { transform: translateX(3px); }
      }
      .az-shake { animation: az-shake 0.4s ease-in-out; }
      .invalid-feedback { display: block; animation: az-fade-up 0.2s ease-out; }
    `;
		document.head.appendChild(style);
	}

	window.FormValidation = {
		init,
		validateField,
		validateForm,
		MSG,
	};

	if (typeof document !== "undefined") {
		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", init);
		} else {
			init();
		}
	}
})();
