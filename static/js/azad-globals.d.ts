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

interface Window {
	SmartPrint?: {
		buildButtons(options: Record<string, any>): DataTableButton[];
		attachTrigger(table: any, triggerSelector: string, options: Record<string, any>): void;
	};
	ActionHelpers?: {
		archivePaymentItem(type: string, id: string, number: string): void;
	};
	applyDataTablePrintStyles?(win: Window): void;
	BarcodeScanner?: new (options: {
		onScan: (code: string) => void;
		minLength?: number;
	}) => { start(): void };
	notify?: {
		show(options: { type: string; title?: string; message: string; duration?: number }): void;
	};
	azad?: Record<string, any>;
	UI?: Record<string, any>;
	submitWithFallback?: (url: string, data: any, method?: string) => Promise<any>;
	fetchWithRetry?: (url: string, options?: RequestInit, retries?: number) => Promise<Response>;
	saveFormState?: () => void;
	undoForm?: () => void;
	redoForm?: () => void;
	deleteItem?: (itemType: string, itemId: string, itemName?: string) => void;
	deleteMultiple?: (itemIds: string[], itemType: string, redirectUrl?: string) => void;
	deleteTableRow?: (rowElement: HTMLElement, confirmMessage?: string) => void;
	restoreItem?: (itemId: string, itemType: string, itemName?: string) => void;
	AzadPrint?: {
		printPageReport(): void;
		printElement(selector: string, options?: Record<string, any>): void;
	};
	initAutoSave?: () => void;
	initProgressIndicators?: () => void;
	initSmartDefaults?: () => void;
	initProductCategoryControls?: (opts: Record<string, any>) => void;
	initCategoryListControls?: (opts: Record<string, any>) => void;
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
	Sortable?: new (element: HTMLElement, options: Record<string, any>) => undefined;
	_mutationPending?: boolean;
	__azadModalStackingBound?: boolean;
	__bootstrapCompatDelegatesBound?: boolean;
	bootstrap?: Record<string, any>;
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
