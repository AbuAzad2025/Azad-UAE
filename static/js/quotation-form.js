(() => {
	const container = document.getElementById("lines-container");
	if (!container) return;

	let lineIndex = parseInt(container.dataset.nextIndex || "0", 10) || 0;
	const autoAdd = container.dataset.autoAdd === "1";

	function addLine() {
		const tpl = document.getElementById("quotation-line-template");
		if (!tpl || !container) return;
		const html = tpl.innerHTML.replace(/__IDX__/g, String(lineIndex));
		const wrapper = document.createElement("div");
		wrapper.innerHTML = html.trim();
		const node = wrapper.firstElementChild;
		if (node) {
			container.appendChild(node);
			lineIndex += 1;
		}
	}

	function removeLine(idx) {
		const el = container.querySelector(`[data-index="${idx}"]`);
		if (el) el.remove();
	}

	window.addLine = addLine;
	window.removeLine = removeLine;

	if (autoAdd) {
		addLine();
	}
})();
