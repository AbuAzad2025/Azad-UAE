/* ==========================================================================
   Maintenance module — client-side behaviour
   Everything here is progressive enhancement: the page works without it
   (the forms are plain POSTs), and this only removes typing and catches
   mistakes before the server does.
   ========================================================================== */

(function () {
  "use strict";

  const MONEY = (value) => {
    const parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  /** Round to 3 decimals the way the server does (0.001 quantum). */
  const round3 = (value) => Math.round((value + Number.EPSILON) * 1000) / 1000;

  /**
   * Recompute a line's net total from its quantity, price and discount.
   * The server recomputes everything anyway; this is only so the operator
   * sees the number they are about to commit.
   */
  function recomputeLine(row) {
    const qty = MONEY(row.querySelector("[data-line-qty]")?.value);
    const price = MONEY(row.querySelector("[data-line-price]")?.value);
    const percent = MONEY(row.querySelector("[data-line-disc-pct]")?.value);
    const value = MONEY(row.querySelector("[data-line-disc-val]")?.value);
    const mode = row.querySelector("[data-line-disc-mode]")?.value || "percent";

    let net = price;
    if (mode === "percent") {
      net = price * (1 - percent / 100);
    } else {
      net = price - value;
    }
    if (net < 0) {
      net = 0;
    }
    const total = round3(qty * net);
    const target = row.querySelector("[data-line-total]");
    if (target) {
      target.textContent = total.toFixed(3);
    }
    return total;
  }

  function initLineRows(root) {
    root.querySelectorAll("[data-line-row]").forEach((row) => {
      row.querySelectorAll("input, select").forEach((input) => {
        input.addEventListener("input", () => recomputeLine(row));
        input.addEventListener("change", () => recomputeLine(row));
      });
      recomputeLine(row);
    });
  }

  /**
   * Keep the discount inputs consistent: a percentage discount and a value
   * discount are alternatives, and the service refuses a line that carries
   * both. Switching the mode clears the other one.
   */
  function initDiscountMode(root) {
    root.querySelectorAll("[data-line-disc-mode]").forEach((select) => {
      select.addEventListener("change", () => {
        const row = select.closest("[data-line-row]");
        if (!row) return;
        const pct = row.querySelector("[data-line-disc-pct]");
        const val = row.querySelector("[data-line-disc-val]");
        if (select.value === "percent") {
          if (val) val.value = "";
        } else if (pct) {
          pct.value = "";
        }
        recomputeLine(row);
      });
    });
  }

  /** The warranty tag legend mirrors the settings page's colour choices. */
  function initWarrantyLegend(root) {
    root.querySelectorAll("[data-warranty-legend]").forEach((legend) => {
      legend.querySelectorAll("[data-legend-swatch]").forEach((swatch) => {
        swatch.style.setProperty("--mnt-tag-color", swatch.dataset.legendSwatch || "#f59e0b");
      });
    });
  }

  function boot() {
    document.querySelectorAll("[data-maintenance-root]").forEach((root) => {
      initLineRows(root);
      initDiscountMode(root);
      initWarrantyLegend(root);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
