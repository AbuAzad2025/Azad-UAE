/**
 * Azad ERP System — Global Type Declarations
 *
 * This file tells PyCharm/WebStorm about globals that are injected at runtime
 * (jQuery plugins, external libraries, server-provided vars, etc.).
 * It has zero runtime impact — it's only for IDE type inference.
 */

// ==================== jQuery plugins ====================

interface JQuery {
	select2(options?: Record<string, any>): this;
	select2(method: string, ...args: any[]): this;
	DataTable(options?: Record<string, any>): any;
	DataTable(method: string, ...args: any[]): any;
	datepicker(options?: Record<string, any>): this;
	tooltip(options?: Record<string, any>): this;
	modal(method: string): this;
	alert(method: string): this;
	tab(method: string): this;
	serialize(): string;
	fadeOut(duration?: number, callback?: () => void): this;
	fadeOut(options?: Record<string, any>): this;
	fadeIn(duration?: number, callback?: () => void): this;
	fadeIn(options?: Record<string, any>): this;
	prop(property: string, value?: any): any;
	attr(attribute: string, value?: any): any;
	data(key: string, value?: any): any;
	html(content?: string): any;
	text(content?: string): any;
	val(value?: any): any;
	trigger(event: string, extraParameters?: any[]): this;
	closest(selector: string): JQuery;
	find(selector: string): JQuery;
	parent(): JQuery;
	append(content: any): this;
	prepend(content: any): this;
	remove(): this;
	empty(): this;
	addClass(className: string): this;
	removeClass(className: string): this;
	toggleClass(className: string): this;
	hasClass(className: string): boolean;
	on(events: string, handler: (...args: any[]) => void): this;
	on(events: string, selector: string, handler: (...args: any[]) => void): this;
	off(events?: string, handler?: (...args: any[]) => void): this;
	each(callback: (index: number, element: any) => void): this;
	css(property: string, value?: any): any;
	keydown(handler: (event: JQueryEventObject) => void): this;
	hover(
		handlerIn: (event: JQueryEventObject) => void,
		handlerOut?: (event: JQueryEventObject) => void,
	): this;
	focus(): this;
	select(): this;
	blur(): this;
	keypress(handler: (event: JQueryEventObject) => void): this;
	after(content: any): this;
	before(content: any): this;
	children(selector?: string): JQuery;
	is(selector: string): boolean;
	offset(): { top: number; left: number };
	animate(
		properties: Record<string, any>,
		duration?: number,
		easing?: string,
		callback?: () => void,
	): this;
	slideUp(duration?: number, callback?: () => void): this;
	slideDown(duration?: number, callback?: () => void): this;
}

interface JQueryEventObject {
	target: EventTarget | null;
	currentTarget: EventTarget | null;
	preventDefault(): void;
	stopPropagation(): void;
	stopImmediatePropagation(): void;
	isDefaultPrevented(): boolean;
	keyCode: number;
	ctrlKey: boolean;
	altKey: boolean;
	shiftKey: boolean;
	key: string;
	data?: any;
	result?: any;
}

interface JQueryStatic {
	fn: Record<string, any> & {
		DataTable: JQueryDataTable;
		dataTable: any;
		select2: any;
		datepicker: any;
		tooltip: any;
		modal: any;
		alert: any;
		tab: any;
	};
	ajaxSetup(options: Record<string, any>): void;
	ajax(options: Record<string, any>): JQueryXHR;
	get(
		url: string,
		data?: any,
		success?: (data: any, textStatus: string, jqXHR: JQueryXHR) => void,
		dataType?: string,
	): JQueryXHR;
	extend(
		deep: boolean | Record<string, any>,
		target: Record<string, any>,
		...sources: Record<string, any>[]
	): Record<string, any>;
	each(collection: any, callback: (index: number, value: any) => void): any;
}

interface JQueryXHR {
	done(callback: (data: any, textStatus: string, jqXHR: JQueryXHR) => void): this;
	fail(callback: (jqXHR: JQueryXHR, textStatus: string, errorThrown: string) => void): this;
	always(callback: (data: any, textStatus: string, jqXHR: JQueryXHR) => void): this;
	then(
		doneCallback: (data: any, textStatus: string, jqXHR: JQueryXHR) => void,
		failCallback?: (jqXHR: JQueryXHR, textStatus: string, errorThrown: string) => void,
	): this;
	status: number;
	responseJSON?: any;
	responseText?: string;
}

// ==================== DataTables plugin ====================

interface JQueryDataTable {
	isDataTable(element: HTMLElement | JQuery): boolean;
	tables(options: { visible: boolean; api: boolean }): any;
	defaults: Record<string, any>;
}

interface DataTableButton {
	extend: string;
	text: string;
	className?: string;
	customize?: (win: Window) => void;
}

interface AzadPrintOptions {
	title?: string;
	headerColor?: string;
	css?: string[];
}

interface LazyLoad {
	sweetalert2(): Promise<unknown>;
	datatables(): Promise<unknown[]>;
	select2(): Promise<unknown>;
	sortable(): Promise<unknown>;
	chartjs(): Promise<unknown>;
	qrcode(): Promise<unknown>;
}

interface SmartSearchItem {
	id?: number | string | null;
	text?: string;
	name?: string;
	phone?: string;
	code?: string;
	balance?: number | string;
	stock?: number | string;
	price?: number | string;
	loading?: boolean;
}

interface SmartSearch {
	esc(v: unknown): string;
	initCustomerSearch(): void;
	initSupplierSearch(): void;
	initProductSearch(): void;
	formatCustomerResult(item: SmartSearchItem): JQuery | string;
	formatCustomerSelection(item: SmartSearchItem): string;
	formatSupplierResult(item: SmartSearchItem): JQuery | string;
	formatSupplierSelection(item: SmartSearchItem): string;
	formatProductResult(item: SmartSearchItem): JQuery | string;
	formatProductSelection(item: SmartSearchItem): string;
	init(): void;
}

interface PosState {
	customer: { id: number | string; text: string; is_walkin?: boolean } | null;
	cart: PosCartItem[];
	lastProductResults: Record<string, unknown>[];
	barcodeScanner: { stop(): void } | null;
	posScale: { connect(): Promise<void> } | null;
	selectedTable: { id: number | string; label: string } | null;
	scaleWeightKg?: number;
	idemKey?: string;
	lastTotals?: Record<string, unknown>;
}

interface PosCartItem {
	id: number | string;
	name: string;
	sku?: string;
	barcode?: string;
	qty: number;
	basePrice: number;
	price: number;
	discountPercent: number;
	is_weight_product?: boolean;
}

interface PosTotals {
	subtotal: number;
	tax: number;
	shipping: number;
	discountAmount: number;
	taxRate: number;
	total: number;
	prices_include_vat: boolean;
}

interface PosPaymentChunk {
	amount: number;
	payment_method: string;
	currency: string;
	exchange_rate: number;
}

interface PosFetchResult {
	ok: boolean;
	data?: unknown;
	error?: string;
}

interface PosOfflineCatalog {
	hydrateCatalog(options?: { warehouseParam?: string }): Promise<unknown>;
	lookupLocalProduct(code: string): Promise<Record<string, unknown> | null>;
	parseScaleBarcodeLocal?(code: string): Record<string, unknown> | null;
}

interface PosScaleSerial {
	new (options: {
		onStableWeight: (kg: number) => void;
		onError: (msg: string) => void;
	}): { connect(): Promise<void> };
	isSupported(): boolean;
}

interface PosScaleUIOptions {
	button: HTMLElement | null;
	scale: { connect(): Promise<void> };
	connectedTitle?: string;
	disconnectedTitle?: string;
}

interface PosCameraScanUIOptions {
	button: HTMLElement | null;
	onScan: (code: string) => void;
	onError: (msg: string) => void;
}

interface PosTerminalOptions {
	button: HTMLElement | null;
	getAmount: () => number;
	getCurrency: () => string;
	onApproved: (result: { intentId: string }) => void;
	onError: (msg: string) => void;
}

interface Window {
	SmartPrint?: {
		buildButtons(options: Record<string, unknown>): DataTableButton[];
		attachTrigger(table: unknown, triggerSelector: string, options: Record<string, unknown>): void;
	};
	ActionHelpers?: {
		archivePaymentItem(type: string, id: string, number: string): void;
	};
	applyDataTablePrintStyles?(win: Window): void;
	BarcodeScanner?: new (options: {
		onScan: (code: string) => void;
		minLength?: number;
	}) => { start(): void; stop(): void };
	notify?: {
		show(options: { type: string; title?: string; message: string; duration?: number }): void;
	};
	azad?: Record<string, unknown>;
	UI?: Record<string, unknown>;
	submitWithFallback?: (url: string, data: unknown, method?: string) => Promise<unknown>;
	fetchWithRetry?: (url: string, options?: RequestInit, retries?: number) => Promise<Response>;
	apiFetch?: (url: string, options?: RequestInit) => Promise<unknown>;
	saveFormState?: () => void;
	undoForm?: () => void;
	redoForm?: () => void;
	deleteItem?: (itemType: string, itemId: string, itemName?: string) => void;
	deleteMultiple?: (itemIds: string[], itemType: string, redirectUrl?: string) => void;
	deleteTableRow?: (rowElement: HTMLElement, confirmMessage?: string) => void;
	restoreItem?: (itemId: string, itemType: string, itemName?: string) => void;
	AzadPrint?: {
		printPageReport(): void;
		printElement(selector: string, options?: AzadPrintOptions): void;
	};
	initAutoSave?: () => void;
	initProgressIndicators?: () => void;
	initSmartDefaults?: () => void;
	initProductCategoryControls?: (opts: Record<string, unknown>) => void;
	initCategoryListControls?: (opts: Record<string, unknown>) => void;
	initCustomerSelect?: () => void;
	initSupplierSelect?: () => void;
	initProductSelect?: () => void;
	APP_INLINE_EDIT_ENABLED?: boolean;
	APP_INLINE_EDIT_ENDPOINT_TEMPLATE?: string;
	_FX_FALLBACK_BASE?: string;
	_CURRENCY_SYMBOL?: string;
	_CURRENCY_NAME_AR?: string;
	_LOG_ENDPOINT?: string;
	_FX_API_URL?: string;
	_API_SEARCH_URL?: string;
	_PURCHASE_CALC_URL?: string;
	_PRICES_INCLUDE_VAT?: boolean;
	_EMPTY_CART_TEXT?: string;
	Sortable?: new (element: HTMLElement, options: Record<string, unknown>) => undefined;
	_mutationPending?: boolean;
	__azadModalStackingBound?: boolean;
	__bootstrapCompatDelegatesBound?: boolean;
	bootstrap?: Record<string, unknown>;
	lazyLoad?: LazyLoad;
	SmartSearch?: SmartSearch;
	printSaleTickets?: (saleId: number | string) => Promise<void>;
	printQueuedCartReceipt?: (
		cart: PosCartItem[],
		totals: PosTotals | Record<string, unknown>,
		payload: Record<string, unknown>,
	) => Promise<void>;
	setupTerminalButton?: (options: PosTerminalOptions) => Promise<unknown>;
	PosScaleSerial?: PosScaleSerial;
	setupPosScaleUI?: (options: PosScaleUIOptions) => void;
	setupCameraScanUI?: (
		options: PosCameraScanUIOptions,
	) => { start?(): void; stop?(): void } | undefined;
	posOfflineCatalog?: PosOfflineCatalog;
	_cfdBroadcast?: {
		sendCart(cart: PosCartItem[], totals: Record<string, unknown>): void;
		setSession(sessionId: number | string | null): void;
	};
	_posFmt?: (n: number | string | null) => string;
	_posToNum?: (v: unknown) => number;
	_posEsc?: (s: unknown) => string;
	_posPriceForCurrency?: (basePrice: number) => number;
	_posCurrencySymbolFor?: (code: string) => string;
	_posState?: PosState;
	_posAddToCart?: (p: Record<string, unknown>, qty?: number) => Promise<void>;
	_posRenderCart?: () => Promise<void>;
	_posRecalc?: () => Promise<PosTotals>;
	_posRenderProductResults?: (res: Record<string, unknown>[]) => void;
	_posRunProductSearch?: (q: string) => Promise<void>;
	_posAddFirstOrLookup?: (q: string) => Promise<void>;
	_posShowAlert?: (msg: string, level?: string) => void;
	_posShowModalAlert?: (modalId: string, msg: string, level?: string) => void;
	_posHideModalAlert?: (modalId: string) => void;
	_posCustomerHint?: () => void;
	_posUpdateCartPrices?: () => Promise<void>;
	_posLoadRateForCurrency?: () => Promise<void>;
	_posSplitEnabled?: () => boolean;
	_posSplitSumRefresh?: () => void;
	_posAddSplitRow?: (amount: number | string, method: string) => void;
	_posReadSplitPayments?: () => PosPaymentChunk[] | null;
	_posResetAfterSale?: () => Promise<void>;
	_posCheckout?: (autoPrint: boolean) => Promise<void>;
	_posHandleScannedCode?: (code: string) => Promise<void>;
	_posLoadCategories?: () => Promise<void>;
	_posLoadProducts?: (categoryId?: string) => Promise<void>;
	_posLoadFloors?: () => Promise<void>;
	_posLoadTables?: (floorId: string) => Promise<void>;
	_posLoadTableOptions?: () => Promise<void>;
	_posToggleTableField?: () => void;
	_posHeldCount?: () => number;
	_posNewCartKey?: () => string;
	_posFetchJson?: (url: string) => Promise<PosFetchResult>;
	_posWarehouseParam?: (sep?: string) => string;
	_posNeedsOverride?: (r: Response, j: { error?: string }) => boolean;
	_posPostWithOverride?: (
		url: string,
		body: Record<string, unknown>,
		action: string,
	) => Promise<{ r: Response; j: Record<string, unknown> }>;
	_posRequestOverrideToken?: (action: string) => Promise<string | null>;
	_posConfirmPin?: () => Promise<void>;
	_posSettlePin?: (token: string | null) => void;
	_posEvaluateUpsell?: () => Promise<void>;
	_posScheduleUpsellEval?: () => void;
	_posRenderUpsellMessages?: (
		container: HTMLElement | null,
		prompts: { message?: string }[],
	) => void;
	_posSyncPay?: () => void;
	onerror?: (
		message: string,
		source?: string,
		lineno?: number,
		colno?: number,
		error?: Error,
	) => boolean;
}

// ==================== External libraries ====================

declare var Swal: any;
declare var toastr: any;
declare var XLSX: any;
declare var io: any;

// ==================== jQuery global (for IIFE call sites) ====================

declare var jQuery: JQueryStatic;

// ==================== CommonJS (for Jest test files) ====================

declare var module: { exports: any };

// ==================== Application globals ====================

declare var SmartSelectors: {
	initProducts(element: HTMLElement): void;
	initCustomers(element: HTMLElement): void;
	initSuppliers(element: HTMLElement): void;
};

// ==================== Jinja template-injected variables ====================
// These are NOT JavaScript globals — they exist only inside Jinja template files
// (*.html) where the Jinja engine injects them as context variables before the
// final JavaScript is rendered. PyCharm's JS parser sees them as unresolved
// references because it doesn't understand Jinja syntax. These declarations
// tell PyCharm "this is a valid identifier that exists at render time."
//
// WARNING: These are template-scoped, NOT runtime-scoped. If a pure JS file
// references these, it IS a real bug.

declare var app_enums: Record<string, any>;
declare var current_user_permissions: string[];
declare var tenant_default_currency: string;
declare var is_foreign_currency: boolean;
declare var tenant_currency_symbol: string;
declare var tenant_currency_name_ar: string;
declare var company_default_currency: string;
declare var system_default_currency: string;
declare var suggested_rate: number;
declare var today: string;
declare var ai_enabled: boolean;
declare var ai_disable_reason: string | null;

// ==================== Jinja template object types ====================
// These declare the shape of Jinja context objects used in templates.
// Example: {{ cheque.amount }} is accessed in templates/cheques/view.html

/** @tutorial This is a Jinja template object, not a JS global. Avoid using outside templates. */
interface JinjaChequeObject {
	id: number;
	cheque_number: string;
	cheque_bank_number: string;
	cheque_type: "incoming" | "outgoing";
	status: string;
	status_ar: string;
	type_ar: string;
	amount: number;
	currency: string;
	exchange_rate: number;
	base_amount: number;
	actual_base_amount: number;
	clearance_exchange_rate: number | null;
	currency_gain_loss: number | null;
	bank_name: string;
	bank_branch: string | null;
	issue_date: string;
	due_date: string;
	deposit_date: string | null;
	clearance_date: string | null;
	drawer_name: string | null;
	drawer_id_number: string | null;
	payee_name: string | null;
	notes: string | null;
	bounce_reason: string | null;
	is_overdue: boolean;
	is_due_soon: boolean;
	days_until_due: number;
	customer: { id: number; name: string } | null;
	supplier: { id: number; name: string } | null;
	user: { username: string } | null;
	created_at: string;
}

declare var cheque: JinjaChequeObject;
