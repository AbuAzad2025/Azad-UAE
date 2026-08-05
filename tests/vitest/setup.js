import { vi } from 'vitest';

Object.defineProperty(global, 'window', {
  value: global,
  writable: true,
  configurable: true,
});

global.document = {
  ...global.document,
  documentElement: { lang: 'ar' },
  body: {
    innerHTML: '',
    appendChild: vi.fn(),
    querySelector: vi.fn(),
    querySelectorAll: vi.fn(() => []),
    removeChild: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(() => true),
  },
  createElement: vi.fn((tag) => {
    const el = {
      tagName: tag.toUpperCase(),
      id: '',
      className: '',
      style: { cssText: '', display: '', opacity: '' },
      innerHTML: '',
      textContent: '',
      value: '',
      type: '',
      name: '',
      required: false,
      minLength: 0,
      maxLength: 0,
      min: '',
      max: '',
      pattern: '',
      dataset: {},
      parentElement: {
        querySelector: vi.fn(() => null),
        appendChild: vi.fn(),
      },
      classList: {
        add: vi.fn(),
        remove: vi.fn(),
        contains: vi.fn(() => false),
      },
      querySelector: vi.fn(() => null),
      querySelectorAll: vi.fn(() => []),
      appendChild: vi.fn(),
      remove: vi.fn(),
      setAttribute: vi.fn(),
      getAttribute: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(() => true),
      setAttribute: vi.fn(),
    };
    if (tag === 'style') {
      el.textContent = '';
    }
    return el;
  }),
  getElementById: vi.fn((id) => {
    if (id === 'toast-container') return null;
    if (id === 'toast-styles') return null;
    if (id === 'azadLoadingOverlay') return null;
    return null;
  }),
  getElementsByTagName: vi.fn(() => []),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(() => true),
};

global.HTMLElement = class HTMLElement {};
global.HTMLInputElement = class extends HTMLElement {
  constructor() {
    super();
    this.type = '';
    this.value = '';
    this.name = '';
    this.required = false;
    this.minLength = 0;
    this.maxLength = 0;
    this.min = '';
    this.max = '';
    this.pattern = '';
    this.dataset = {};
    this.parentElement = global.document.createElement('div');
    this.classList = { add: vi.fn(), remove: vi.fn(), contains: vi.fn(() => false) };
  }
};
global.HTMLSelectElement = class extends HTMLElement {
  constructor() {
    super();
    this.value = '';
    this.name = '';
    this.required = false;
    this.options = [];
    this.querySelector = vi.fn(() => null);
  }
};
global.HTMLFormElement = class extends HTMLElement {
  constructor() {
    super();
    this.querySelectorAll = vi.fn(() => []);
    this.setAttribute = vi.fn();
    this.addEventListener = vi.fn();
    this.dispatchEvent = vi.fn((e) => { if (e.cancelable) e.preventDefault = vi.fn(); });
  }
};
global.Audio = class Audio {
  constructor() { this.src = ''; }
  play() { return Promise.resolve(); }
  pause() {}
};

global.requestAnimationFrame = vi.fn((cb) => setTimeout(cb, 0));
global.setTimeout = global.setTimeout;
global.clearTimeout = global.clearTimeout;
Object.defineProperty(global, 'navigator', {
  value: { vibrate: vi.fn() },
  writable: true,
  configurable: true,
});