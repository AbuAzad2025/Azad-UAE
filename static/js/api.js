/**
 * Central API client with double-submit protection.
 *
 * The `_submitting` flag is reset in a `finally` block so a network or
 * parsing error can never leave the UI permanently locked.
 */
(function () {
  "use strict";

  let _submitting = false;

  function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute("content") : "";
  }

  function mergeHeaders(extra) {
    const headers = {
      "X-Requested-With": "XMLHttpRequest",
      "X-CSRFToken": getCsrfToken(),
    };
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        headers[key] = extra[key];
      });
    }
    return headers;
  }

  window.api = {
    isSubmitting: function () {
      return _submitting;
    },

    /**
     * Fetch wrapper that prevents concurrent submissions.
     * The flag is always reset after the request finishes or throws.
     */
    fetch: async function (url, options) {
      if (_submitting) {
        return Promise.reject(new Error("A request is already in progress."));
      }
      _submitting = true;
      try {
        return await fetch(url, options);
      } finally {
        _submitting = false;
      }
    },

    /**
     * Convenience POST helper for JSON payloads.
     */
    post: async function (url, body, options) {
      options = options || {};
      return this.fetch(url, {
        method: "POST",
        headers: mergeHeaders(options.headers),
        body: JSON.stringify(body),
        ...options,
      });
    },

    /**
     * Convenience GET helper.
     */
    get: async function (url, options) {
      options = options || {};
      return this.fetch(url, {
        method: "GET",
        headers: mergeHeaders(options.headers),
        ...options,
      });
    },
  };
})();
