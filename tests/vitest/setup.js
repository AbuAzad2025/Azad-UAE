import { vi } from 'vitest';

// Minimal jQuery global mock — classic scripts reference `$`/`window.$`.
const jqueryChainable = () => {
  const api = {
    on: () => api,
    off: () => api,
    trigger: () => api,
    attr: () => undefined,
    val: () => '',
    find: () => api,
    each: () => api,
    append: () => api,
    remove: () => api,
    addClass: () => api,
    removeClass: () => api,
    hasClass: () => false,
    css: () => api,
    show: () => api,
    hide: () => api,
    html: () => api,
    text: () => api,
    data: () => undefined,
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
  api.attr = (name) => {
    if (name === 'content') return '';
    return undefined;
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
