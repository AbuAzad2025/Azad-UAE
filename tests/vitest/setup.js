import { vi } from 'vitest';

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
