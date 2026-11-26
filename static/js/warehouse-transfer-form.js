/* Transfer form: populate selectors and manage line rows.
 * Exposes window.addLine / window.removeLine so the shared CSP-safe delegated
 * [data-line-action] handler in base.html can drive the buttons.
 */
(() => {
	const t = (key) => (window.I18N_TEXT && window.I18N_TEXT[key]) || key;
	const lines = document.getElementById("lines-container");
	if (!lines) return;

	let nextIndex = 0;

	async function fillSelect(select, url, label) {
		if (!select) return;
		try {
			const res = await fetch(url, {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			});
			if (!res.ok) return;
			const body = await res.json();
			const rows = (body && body.data && body.data.results) || (body && body.data) || [];
			rows.forEach((row) => {
				const option = document.createElement("option");
				option.value = String(row.id);
				option.textContent = row.name || row.text || label;
				select.appendChild(option);
			});
		} catch (_) {
			/* leave the placeholder option in place */
		}
	}

	fillSelect(document.getElementById("f_from_warehouse_id"), "/api/warehouses");
	fillSelect(document.getElementById("f_to_warehouse_id"), "/api/warehouses");

	const makeRow = (index) => {
		const row = document.createElement("div");
		row.className = "row g-2 mb-2 transfer-line";
		row.dataset.index = String(index);
		const fields = [
			["product_id", "select"],
			["quantity", "number"],
			["notes", "text"],
		];
		fields.forEach(([field, type]) => {
			const col = document.createElement("div");
			col.className = type === "text" ? "col-md-6" : "col-md-3";
			const input =
				type === "select" ? document.createElement("select") : document.createElement("input");
			input.name = `lines-${index}-${field}`;
			input.required = field !== "notes";
			if (type === "select") {
				input.className = "form-select product-select";
				const placeholder = document.createElement("option");
				placeholder.value = "";
				placeholder.textContent = t("Select");
				input.appendChild(placeholder);
				fillSelect(input, "/api/products");
			} else {
				input.type = type;
				input.className = "form-control";
				if (type === "number") {
					input.min = "0.001";
					input.step = "0.001";
					input.value = "1";
				}
				input.setAttribute("aria-label", field);
			}
			col.appendChild(input);
			row.appendChild(col);
		});
		const removeCol = document.createElement("div");
		removeCol.className = "col-md-3 d-flex align-items-end";
		const remove = document.createElement("button");
		remove.type = "button";
		remove.className = "btn btn-sm btn-danger";
		remove.textContent = t("Delete");
		remove.addEventListener("click", () => row.remove());
		removeCol.appendChild(remove);
		row.appendChild(removeCol);
		return row;
	};

	function addLine() {
		const row = makeRow(nextIndex++);
		lines.appendChild(row);
		return row;
	}

	function removeLine(index) {
		const row = lines.querySelector(`[data-index="${Number(index)}"]`);
		if (row) row.remove();
	}

	window.addLine = addLine;
	window.removeLine = removeLine;
})();
