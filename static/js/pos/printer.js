const autoPrintSale = (saleId) => {
	if (saleId && window.printSaleTickets) {
		void window.printSaleTickets(saleId);
	}
};
const autoPrintQueuedReceipt = (cart, totals, payload) => {
	if (window.printQueuedCartReceipt) {
		void window.printQueuedCartReceipt(cart, totals, payload);
	}
};

export { autoPrintQueuedReceipt, autoPrintSale };
