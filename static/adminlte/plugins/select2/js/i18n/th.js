/*! Select2 4.0.13 | https://github.com/select2/select2/blob/master/LICENSE.md */

!(() => {
	if (jQuery && jQuery.fn && jQuery.fn.select2 && jQuery.fn.select2.amd)
		var n = jQuery.fn.select2.amd;
	n.define("select2/i18n/th", [], () => ({
		errorLoading: () => "ไม่สามารถค้นข้อมูลได้",
		inputTooLong: (n) =>
			"โปรดลบออก " + (n.input.length - n.maximum) + " ตัวอักษร",
		inputTooShort: (n) =>
			"โปรดพิมพ์เพิ่มอีก " + (n.minimum - n.input.length) + " ตัวอักษร",
		loadingMore: () => "กำลังค้นข้อมูลเพิ่ม…",
		maximumSelected: (n) => "คุณสามารถเลือกได้ไม่เกิน " + n.maximum + " รายการ",
		noResults: () => "ไม่พบข้อมูล",
		searching: () => "กำลังค้นข้อมูล…",
		removeAllItems: () => "ลบรายการทั้งหมด",
	})),
		n.define,
		n.require;
})();
