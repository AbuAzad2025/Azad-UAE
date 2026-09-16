import { vi, beforeEach } from 'vitest';

// Save native window.addEventListener before any test can mock it (used by
// gap100_base to reliably clean leaked error handlers across vi.resetModules).
if (typeof window !== 'undefined' && typeof EventTarget !== 'undefined' && EventTarget.prototype.addEventListener) {
  try {
    const ETProto = EventTarget.prototype;
    const _origProtoAdd = ETProto.addEventListener;
    const _origProtoRemove = ETProto.removeEventListener;
    globalThis.__trackedErrorHandlers = [];
    // Wrap prototype to catch all EventTarget listeners
    ETProto.addEventListener = function (type, handler, ...rest) {
      if ((type === "error" || type === "unhandledrejection") && typeof handler === "function") {
        globalThis.__trackedErrorHandlers.push({ target: this, type, handler });
      }
      return _origProtoAdd.call(this, type, handler, ...rest);
    };
    ETProto.removeEventListener = function (type, handler, ...rest) {
      const idx = globalThis.__trackedErrorHandlers.findIndex((e) => e.target === this && e.type === type && e.handler === handler);
      if (idx !== -1) globalThis.__trackedErrorHandlers.splice(idx, 1);
      return _origProtoRemove.call(this, type, handler, ...rest);
    };
    // Also wrap window's own addEventListener if it shadows prototype (jsdom does)
    const winOwnAdd = window.addEventListener;
    const winOwnRemove = window.removeEventListener;
    if (winOwnAdd !== ETProto.addEventListener) {
      globalThis.__nativeWindowAddEventListener = winOwnAdd.bind(window);
      globalThis.__nativeWindowRemoveEventListener = winOwnRemove.bind(window);
      const winWrapper = function (type, handler, ...rest) {
        if ((type === "error" || type === "unhandledrejection") && typeof handler === "function") {
          const already = globalThis.__trackedErrorHandlers.some((e) => e.target === this && e.type === type && e.handler === handler);
          if (!already) globalThis.__trackedErrorHandlers.push({ target: this, type, handler });
        }
        return winOwnAdd.call(this, type, handler, ...rest);
      };
      winWrapper.__isTrackedWrapper = true;
      window.addEventListener = winWrapper;
      window.removeEventListener = function (type, handler, ...rest) {
        const idx = globalThis.__trackedErrorHandlers.findIndex((e) => e.target === this && e.type === type && e.handler === handler);
        if (idx !== -1) globalThis.__trackedErrorHandlers.splice(idx, 1);
        return winOwnRemove.call(this, type, handler, ...rest);
      };
    } else {
      globalThis.__nativeWindowAddEventListener = _origProtoAdd.bind(window);
      globalThis.__nativeWindowRemoveEventListener = _origProtoRemove.bind(window);
    }
    globalThis.__cleanupLeakedErrorHandlers = () => {
      for (const { target, type, handler } of globalThis.__trackedErrorHandlers.splice(0)) {
        try { _origProtoRemove.call(target, type, handler); } catch (_) {}
        try { winOwnRemove.call(target, type, handler); } catch (_) {}
      }
    };
    // Ensure window wrapper survives vi.restoreAllMocks (which restores window.addEventListener to native)
    const _origRestoreAllMocks = vi.restoreAllMocks.bind(vi);
    vi.restoreAllMocks = function (...args) {
      const res = _origRestoreAllMocks(...args);
      try {
        if (!window.addEventListener.__isTrackedWrapper) {
          const nat = globalThis.__nativeWindowAddEventListener;
          if (nat) {
            const wr = function (type, handler, ...rest) {
              if ((type === "error" || type === "unhandledrejection") && typeof handler === "function") {
                const already = globalThis.__trackedErrorHandlers.some((e) => e.target === this && e.type === type && e.handler === handler);
                if (!already) globalThis.__trackedErrorHandlers.push({ target: this, type, handler });
              }
              return nat.call(this, type, handler, ...rest);
            };
            wr.__isTrackedWrapper = true;
            window.addEventListener = wr;
          }
        }
      } catch (_) {}
      return res;
    };
    // Global beforeEach to clean leaked handlers before every test (prevents cross-file pollution)
    beforeEach(() => {
      try { globalThis.__cleanupLeakedErrorHandlers?.(); } catch (_) {}
      try { window.addEventListener.mockRestore?.(); } catch (_) {}
      if (!window.addEventListener.__isTrackedWrapper) {
        const nat = globalThis.__nativeWindowAddEventListener;
        if (nat) {
          const wr = function (type, handler, ...rest) {
            if ((type === "error" || type === "unhandledrejection") && typeof handler === "function") {
              const already = globalThis.__trackedErrorHandlers.some((e) => e.target === this && e.type === type && e.handler === handler);
              if (!already) globalThis.__trackedErrorHandlers.push({ target: this, type, handler });
            }
            return nat.call(this, type, handler, ...rest);
          };
          wr.__isTrackedWrapper = true;
          window.addEventListener = wr;
        }
      }
    });
  } catch (_) {}
}

// Emulate i18n.js global so classic scripts can call bare `t()` (the browser
// loads static/js/i18n.js before POS modules). Identity passthrough keeps the
// Arabic source string intact for assertions.
const _t = (key) => {
  const lang = window.I18N_LANG || document.documentElement.lang || 'ar';
  const dict = window.I18N_TRANSLATIONS;
  if (dict && dict[key] && dict[key][lang]) return dict[key][lang];
  if (dict && dict[key] && dict[key].en) return dict[key].en;
  return key;
};
globalThis.t = _t;
if (typeof window !== 'undefined') window.t = _t;

// Mock translations for frontend unit tests so window.t() returns the expected
// Arabic strings used in assertions.
if (typeof window !== 'undefined') {
  window.I18N_TRANSLATIONS = {
    automatic: { ar: 'تلقائي', en: 'Automatic' },
    bad_request: { ar: 'طلب غير صالح', en: 'Bad request' },
    close_notification: { ar: 'إغلاق الإشعار', en: 'Close notification' },
    conflict: { ar: 'تعارض في البيانات — حدّث الصفحة وحاول مجدداً', en: 'Data conflict' },
    connection_error: { ar: 'تعذر الاتصال بالخادم — تحقق من اتصالك بالإنترنت', en: 'Connection error' },
    currency_aed: { ar: 'درهم إماراتي', en: 'UAE Dirham' },
    currency_egp: { ar: 'جنيه مصري', en: 'Egyptian Pound' },
    currency_eur: { ar: 'يورو', en: 'Euro' },
    currency_gbp: { ar: 'جنيه إسترليني', en: 'British Pound' },
    currency_ils: { ar: 'شيكل فلسطيني', en: 'Israeli Shekel' },
    currency_jod: { ar: 'دينار أردني', en: 'Jordanian Dinar' },
    currency_sar: { ar: 'ريال سعودي', en: 'Saudi Riyal' },
    currency_usd: { ar: 'دولار أمريكي', en: 'US Dollar' },
    desktop: { ar: 'كمبيوتر', en: 'Desktop' },
    enter_valid_values: { ar: 'أدخل قيم صحيحة', en: 'Enter valid values' },
    error: { ar: 'خطأ', en: 'Error' },
    estimated_rate: { ar: 'سعر تقديري', en: 'Estimated rate' },
    form_expired: { ar: 'انتهت صلاحية النموذج — حدّث الصفحة', en: 'Form expired' },
    in_stock: { ar: 'متوفر', en: 'In Stock' },
    info: { ar: 'معلومة', en: 'Info' },
    interest_amount: { ar: 'الفائدة', en: 'Interest' },
    last_saved_rate: { ar: 'آخر سعر محفوظ', en: 'Last saved rate' },
    last_updated: { ar: 'آخر تحديث', en: 'Last updated' },
    live_rate: { ar: 'مباشر', en: 'Live' },
    loading_ellipsis: { ar: 'جارٍ التحميل...', en: 'Loading...' },
    mobile: { ar: 'جوال', en: 'Mobile' },
    monthly_installment: { ar: 'القسط', en: 'Installment' },
    no_results: { ar: 'لا توجد نتائج', en: 'No results' },
    notifications: { ar: 'الإشعارات', en: 'Notifications' },
    out_of_stock: { ar: 'غير متوفر', en: 'Out of Stock' },
    paid_status: { ar: 'مدفوع', en: 'Paid' },
    page_total: { ar: 'إجمالي الصفحة', en: 'Page total' },
    partial: { ar: 'جزئي', en: 'Partial' },
    permission_denied: { ar: 'ليس لديك صلاحية لتنفيذ هذا الإجراء', en: 'Permission denied' },
    Print: { ar: 'طباعة', en: 'Print' },
    processing: { ar: 'جاري المعالجة...', en: 'Processing...' },
    profit: { ar: 'الربح', en: 'Profit' },
    sales_register: { ar: 'سجل المبيعات', en: 'Sales Register' },
    saved_locally: { ar: 'تم الحفظ محلياً', en: 'Saved locally' },
    autosaved_locally: { ar: 'تم حفظ البيانات تلقائياً على هذا الجهاز فقط', en: 'Autosaved locally' },
    search_customers: { ar: 'ابحث عن زبون...', en: 'Search customers...' },
    search_error: { ar: 'خطأ في البحث', en: 'Search error' },
    search_products: { ar: 'ابحث عن منتج...', en: 'Search products...' },
    search_suppliers: { ar: 'ابحث عن مورد...', en: 'Search suppliers...' },
    searching: { ar: 'جاري البحث...', en: 'Searching...' },
    select_placeholder: { ar: 'اختر...', en: 'Select...' },
    server_error: { ar: 'خطأ في الخادم — حاول مرة أخرى لاحقاً', en: 'Server error' },
    session_expired: { ar: 'انتهت الجلسة — يرجى تسجيل الدخول مجدداً', en: 'Session expired' },
    success: { ar: 'نجاح', en: 'Success' },
    system_alert: { ar: 'تنبيه النظام', en: 'System alert' },
    too_many_requests: { ar: 'طلبات كثيرة — انتظر قليلاً ثم أعد المحاولة', en: 'Too many requests' },
    total_label: { ar: 'الإجمالي', en: 'Total' },
    unpaid_status: { ar: 'آجل', en: 'Unpaid' },
    unexpected_error: { ar: 'خطأ غير متوقع — حاول مرة أخرى', en: 'Unexpected error' },
    warning: { ar: 'تحذير', en: 'Warning' },
  };
}

// Minimal jQuery global mock — classic scripts reference `$`/`window.$`.
const jqueryChainable = () => {
  const store = {};
  const api = {
    on: () => api,
    off: () => api,
    trigger: () => api,
    each: () => api,
    append: () => api,
    remove: () => api,
    addClass: () => api,
    removeClass: () => api,
    hasClass: () => false,
    css: () => api,
    show: () => api,
    hide: () => api,
    closest: () => api,
    find: () => api,
    prop: () => undefined,
    is: () => false,
    attr: (name, val) => {
      if (val !== undefined) {
        store['attr:' + name] = val;
        return api;
      }
      return store['attr:' + name] ?? undefined;
    },
    val: (val) => {
      if (val !== undefined) {
        store.val = val;
        return api;
      }
      return store.val ?? '';
    },
    html: (val) => {
      if (val !== undefined) {
        store.html = val;
        return api;
      }
      return store.html ?? '';
    },
    text: (val) => {
      if (val !== undefined) {
        store.text = val;
        return api;
      }
      return store.text ?? '';
    },
    data: (key, val) => {
      if (val !== undefined) {
        store['data:' + key] = val;
        return api;
      }
      return store['data:' + key] ?? undefined;
    },
    ready: (fn) => {
      if (typeof fn === 'function') fn();
      return api;
    },
    ajaxSetup: () => api,
    parent: () => ({ querySelector: () => null, appendChild: () => {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
    setRequestHeader: vi.fn(),
  };
  return api;
};

const $ = (selector) => {
  const api = jqueryChainable();
  if (typeof selector === 'function') {
    api.ready(selector);
    return api;
  }
  api.attr = (name, val) => {
    if (name === 'content') return '';
    if (val !== undefined) {
      api.__store = api.__store || {};
      api.__store['attr:' + name] = val;
      return api;
    }
    return (api.__store && api.__store['attr:' + name]) ?? undefined;
  };
  return api;
};
$.ajaxSetup = vi.fn();
$.ajax = () => Promise.resolve();
$.notify = () => {};
$.fn = {};

global.$ = $;
if (typeof window !== 'undefined') window.$ = $;

// jsdom lacks Audio / requestAnimationFrame / vibrate shims used by the modules.
if (typeof window !== 'undefined' && typeof window.Audio === 'undefined') {
  class AudioShim {
    constructor() {
      this.volume = 1;
    }
    play() {
      return Promise.resolve();
    }
    pause() {}
  }
  window.Audio = AudioShim;
  global.Audio = AudioShim;
}

if (typeof global.requestAnimationFrame === 'undefined') {
  global.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  global.cancelAnimationFrame = (id) => clearTimeout(id);
}

try {
  if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'undefined') {
    Object.defineProperty(navigator, 'vibrate', { value: vi.fn(), configurable: true });
  }
} catch (_) {}
