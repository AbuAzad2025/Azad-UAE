export const $ = (selector) => {
  const el = {
    selector,
    on: () => el,
    off: () => el,
    trigger: () => el,
    attr: () => el,
    val: () => '',
    find: () => el,
    each: (fn) => fn(0, {}) || el,
    append: () => el,
    remove: () => el,
    addClass: () => el,
    removeClass: () => el,
    hasClass: () => false,
    css: () => el,
    show: () => el,
    hide: () => el,
    html: () => '',
    text: () => '',
    data: () => undefined,
    parent: () => ({ querySelector: () => null, appendChild: () => {} }),
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  return el;
};
$.ajaxSetup = () => {};
$.ajax = () => Promise.resolve();
$.fn = { init: () => $ };