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
	};
	const PHONE_RE = /^[+]?[0-9\s-]{8,20}$/;

	function showError(input, msg) {
		input.classList.add("is-invalid");
		let fb = input.parentElement.querySelector(".invalid-feedback");
		if (!fb) {
			fb = document.createElement("div");
			fb.className = "invalid-feedback";
			input.parentElement.appendChild(fb);
		}
		fb.textContent = msg;
	}

	function clearError(input) {
		input.classList.remove("is-invalid");
		const fb = input.parentElement.querySelector(".invalid-feedback");
		if (fb) fb.textContent = "";
	}

	function validateField(input) {
		const val = input.value.trim();
		const type = input.type;
		const name = input.name;
		let err = null;

		if (input.required && !val) {
			err = MSG.required;
		} else if (val) {
			if (type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) {
				err = MSG.email;
			} else if (name.includes("phone") && !PHONE_RE.test(val)) {
				err = MSG.phone;
			} else if (input.minLength > 0 && val.length < input.minLength) {
				err = MSG.minlength.replace("{0}", input.minLength);
			} else if (input.maxLength > 0 && val.length > input.maxLength) {
				err = MSG.maxlength.replace("{0}", input.maxLength);
			} else if (input.pattern) {
				const re = new RegExp(input.pattern);
				if (!re.test(val)) err = MSG.pattern;
			} else if (input.min && Number(val) < Number(input.min)) {
				err = MSG.min.replace("{0}", input.min);
			} else if (input.max && Number(val) > Number(input.max)) {
				err = MSG.max.replace("{0}", input.max);
			}
		}

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
		inputs.forEach((input) => {
			if (!validateField(input)) ok = false;
		});
		return ok;
	}

	function init() {
		document.querySelectorAll("form.needs-validation").forEach((form) => {
			form.setAttribute("novalidate", "");
			form.addEventListener("submit", (e) => {
				if (!validateForm(form)) {
					e.preventDefault();
					e.stopPropagation();
				}
			});
			const inputs = form.querySelectorAll("input, select, textarea");
			inputs.forEach((input) => {
				input.addEventListener("blur", () => {
					validateField(input);
				});
				input.addEventListener("input", () => {
					if (input.classList.contains("is-invalid")) validateField(input);
				});
			});
		});
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", init);
	} else {
		init();
	}
})();
