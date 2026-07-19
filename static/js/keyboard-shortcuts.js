/**
 * Keyboard Shortcuts System
 * اختصارات لوحة المفاتيح الاحترافية
 */

class KeyboardShortcuts {
	constructor() {
		this.shortcuts = new Map();
		this.isEnabled = true;
		this.init();
	}

	init() {
		document.addEventListener("keydown", this.handleKeyPress.bind(this));
		this.registerDefaultShortcuts();
		this.showHelpButton();
	}

	register(key, callback, description = "") {
		this.shortcuts.set(key.toLowerCase(), {
			callback,
			description,
		});
	}

	handleKeyPress(e) {
		if (!this.isEnabled) return;

		// Don't trigger in input fields (unless Ctrl/Alt is pressed)
		if (
			["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName) &&
			!e.ctrlKey &&
			!e.altKey &&
			!e.metaKey
		) {
			return;
		}

		const key = this.getKeyString(e);
		const shortcut = this.shortcuts.get(key);

		if (shortcut) {
			e.preventDefault();
			shortcut.callback(e);
		}
	}

	getKeyString(e) {
		const parts = [];
		if (e.ctrlKey || e.metaKey) parts.push("ctrl");
		if (e.altKey) parts.push("alt");
		if (e.shiftKey) parts.push("shift");
		parts.push(e.key.toLowerCase());
		return parts.join("+");
	}

	registerDefaultShortcuts() {
		// Navigation
		this.register(
			"alt+h",
			() => {
				window.location.href = "/";
			},
			"الذهاب للرئيسية",
		);

		this.register(
			"alt+s",
			() => {
				const salesBtn = document.querySelector('a[href*="sales"]');
				if (salesBtn) salesBtn.click();
			},
			"فتح المبيعات",
		);

		this.register(
			"alt+c",
			() => {
				const customersBtn = document.querySelector('a[href*="customers"]');
				if (customersBtn) customersBtn.click();
			},
			"فتح الزبائن",
		);

		this.register(
			"alt+p",
			() => {
				const productsBtn = document.querySelector('a[href*="products"]');
				if (productsBtn) productsBtn.click();
			},
			"فتح المنتجات",
		);

		// Actions
		this.register(
			"ctrl+n",
			() => {
				const createBtn = document.querySelector(
					'.btn-primary[href*="create"]',
				);
				if (createBtn) {
					createBtn.click();
				} else {
					notify.info("لا يوجد زر إنشاء في هذه الصفحة");
				}
			},
			"إنشاء جديد",
		);

		this.register(
			"ctrl+s",
			() => {
				const form = document.querySelector("form");
				if (form) {
					form.dispatchEvent(
						new Event("submit", { cancelable: true, bubbles: true }),
					);
				}
			},
			"حفظ النموذج",
		);

		this.register(
			"escape",
			() => {
				// Close modals
				const modal = document.querySelector(".modal.show");
				if (modal) {
					$(modal).modal("hide");
					return;
				}

				// Close notifications
				const toasts = document.querySelectorAll(".toast");
				toasts.forEach((toast) => toast.remove());
			},
			"إغلاق/إلغاء",
		);

		// Search
		this.register(
			"ctrl+k",
			() => {
				const searchInput = document.querySelector(
					'input[type="search"], input[placeholder*="بحث"]',
				);
				if (searchInput) {
					searchInput.focus();
					searchInput.select();
				}
			},
			"البحث السريع",
		);

		// DataTable shortcuts
		this.register(
			"ctrl+e",
			() => {
				const exportBtn = document.querySelector(
					".buttons-excel, .buttons-csv",
				);
				if (exportBtn) {
					exportBtn.click();
					notify.success("جاري تصدير البيانات...");
				}
			},
			"تصدير البيانات",
		);

		this.register(
			"ctrl+p",
			() => {
				window.print();
			},
			"طباعة",
		);

		// Help
		this.register(
			"?",
			() => {
				this.showHelp();
			},
			"عرض المساعدة",
		);

		this.register(
			"ctrl+/",
			() => {
				this.showHelp();
			},
			"عرض الاختصارات",
		);

		// Sidebar toggle
		this.register(
			"ctrl+b",
			() => {
				$('[data-widget="pushmenu"]').trigger("click");
			},
			"إخفاء/إظهار القائمة",
		);
	}

	showHelpButton() {
		if (document.getElementById("shortcuts-help-btn")) return;

		const btn = document.createElement("button");
		btn.id = "shortcuts-help-btn";
		btn.className = "btn btn-sm btn-info";
		btn.innerHTML = '<i class="fas fa-keyboard"></i>';
		btn.title = "اختصارات لوحة المفاتيح (?)";
		btn.style.cssText = `
            position: fixed;
            bottom: 20px;
            left: 20px;
            z-index: 9999;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        `;
		btn.onclick = () => this.showHelp();
		document.body.appendChild(btn);
	}

	showHelp() {
		const shortcuts = Array.from(this.shortcuts.entries())
			.filter(([_, v]) => v.description)
			.map(
				([key, value]) => `
                <tr>
                    <td><kbd class="shortcut-key">${key}</kbd></td>
                    <td>${value.description}</td>
                </tr>
            `,
			)
			.join("");

		const modal = `
            <div class="modal fade" id="shortcuts-modal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-info text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-keyboard mr-2"></i>
                                اختصارات لوحة المفاتيح
                            </h5>
                            <button type="button" class="close text-white" data-dismiss="modal">
                                <span>×</span>
                            </button>
                        </div>
                        <div class="modal-body">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th style="width: 200px">الاختصار</th>
                                        <th>الوصف</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${shortcuts}
                                </tbody>
                            </table>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-dismiss="modal">إغلاق</button>
                        </div>
                    </div>
                </div>
            </div>
            <style>
                .shortcut-key {
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 4px 8px;
                    border-radius: 5px;
                    font-size: 12px;
                    font-weight: 600;
                    margin: 0 2px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                    white-space: nowrap;
                }
            </style>
        `;

		// Remove old modal
		$("#shortcuts-modal").remove();

		// Add and show new modal
		$(modal).appendTo("body").modal("show");
	}

	// noinspection JSUnusedGlobalSymbols
	disable() {
		this.isEnabled = false;
	}

	enable() {
		this.isEnabled = true;
	}
}

// Initialize
window.shortcuts = new KeyboardShortcuts();

// Show notification on first load
$(document).ready(() => {
	if (!localStorage.getItem("shortcuts-shown")) {
		setTimeout(() => {
			notify.info("اضغط ? لعرض اختصارات لوحة المفاتيح", "نصيحة سريعة");
			localStorage.setItem("shortcuts-shown", "true");
		}, 2000);
	}
});
