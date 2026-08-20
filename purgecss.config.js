/**
 * PurgeCSS configuration — ANALYSIS / OPT-IN USE ONLY.
 *
 * Purpose: measure how much of the large custom stylesheets is actually
 * referenced from Jinja templates / JS, and produce purged copies for review.
 * Output goes to the gitignored `coverage-frontend/purgecss/` directory.
 * It NEVER overwrites sources in `static/css/`.
 *
 * Run:  npm run css:purge
 *
 * Rules wrapped in `/* purgecss start ignore * / ... /* purgecss end ignore * /`
 * (project convention, see AGENTS.md) are always kept.
 *
 * Before adopting any purged output, review the rejected selectors —
 * classes injected at runtime by JS or stored in the DB can be false-positives.
 */

// Classes that JS libraries or runtime code toggle dynamically and that raw
// template scanning cannot see. Keep the list generous: a wrong purge is a
// broken UI in production.
const SAFELIST = {
  standard: [
    // Bootstrap runtime state
    /^(show|fade|collapsing|collapse|active|disabled|was-validated|is-valid|is-invalid)$/,
    /^modal(-open|-backdrop|-static)?$/,
    /^offcanvas/,
    /^toast/,
    /^tooltip/,
    /^popover/,
    /^dropdown-(menu|item|toggle|divider|header)/,
    /^nav(-link|-item|-tabs|-pills)?$/,
    /^tab-(pane|content)$/,
    /^alert-/,
    /^badge/,
    /^spinner-/,
    /^placeholder/,
    // DataTables / Select2 / SweetAlert2 runtime classes
    /^dt-/,
    /^dataTables/,
    /^select2/,
    /^swal2-/,
    // FontAwesome (kept even if css is analyzed without the FA file)
    /^fa[bsrl]?$|^fa-/,
    // App runtime: theme switcher, RTL/LTR, POS dynamic, toasts
    /^pos-/,
    /^erp-theme-/,
    /^(rtl|ltr|dark|light|theme-)/,
    /^(flash|notification|toast)-/,
    /^azad-/,
  ],
  deep: [/select2/, /swal2/, /dataTables/],
  greedy: [/pos-page--grid/],
};

module.exports = {
  content: [
    "templates/**/*.html",
    "static/js/**/*.js",
    "!static/js/**/*.min.js",
  ],
  css: [
    "static/css/erp-theme-unified.css",
    "static/css/pos-unified.css",
    "static/css/landing.css",
    "static/css/landing-page-en.css",
    "static/css/accessibility.css",
  ],
  output: "coverage-frontend/purgecss/",
  safelist: SAFELIST,
  // Jinja expressions, Alpine/JS template strings and HTML attributes all
  // appear as raw text; this extractor keeps colon/slash variants too.
  defaultExtractor: (content) => content.match(/[A-Za-z0-9_:/-]+/g) || [],
  // Dynamic CSS variables & keyframes are cheap to keep correct.
  variables: true,
  keyframes: true,
  fontFace: true,
};
