(function () {
  "use strict";

  function fmt(n) {
    var x = Number(n || 0);
    if (!isFinite(x)) x = 0;
    return x.toFixed(2);
  }

  function directionBadge(dir) {
    if (dir === "IN") return '<span class="badge bg-success">وارد</span>';
    if (dir === "OUT") return '<span class="badge bg-danger">صادر</span>';
    return '<span class="badge bg-secondary">—</span>';
  }

  function showMethodSection(method) {
    var ids = ["sec-cheque","sec-bank","sec-card","sec-online"];
    ids.forEach(function(id){ var el=document.getElementById(id); if(el) el.classList.add("d-none"); });
    if (!method) return;
    if (method === "cheque") document.getElementById("sec-cheque")?.classList.remove("d-none");
    else if (method === "bank") document.getElementById("sec-bank")?.classList.remove("d-none");
    else if (method === "card") document.getElementById("sec-card")?.classList.remove("d-none");
    else if (method === "online") document.getElementById("sec-online")?.classList.remove("d-none");
  }

  function normalizeArabicDigits(str) {
    if (!str) return "";
    return String(str)
      .replace(/[٠-٩]/g, function(d){ return "٠١٢٣٤٥٦٧٨٩".indexOf(d); })
      .replace(/[٬،\s]/g, "")
      .replace("٫", ".")
      .replace(",", ".");
  }

  function sanitizeAmountInput(raw) {
    var s = normalizeArabicDigits(raw);
    s = s.replace(/[^0-9.]/g, "");
    var firstDot = s.indexOf(".");
    if (firstDot !== -1) s = s.slice(0, firstDot + 1) + s.slice(firstDot + 1).replace(/\./g, "");
    return s;
  }

  function toNumber(val) {
    var s = sanitizeAmountInput(val);
    var n = parseFloat(s);
    return isNaN(n) ? 0 : n;
  }

  function openSettlementModal(payload) {
    var modalEl = document.getElementById("settlementModal");
    if (!modalEl) return;
    var bsModal = (window.bootstrap && window.bootstrap.Modal) ? new bootstrap.Modal(modalEl) : null;

    var dom = {
      name: document.getElementById("stlName"),
      balance: document.getElementById("stlBalance"),
      amount: document.getElementById("stlAmount"),
      currency: document.getElementById("stlCurrency"),
      method: document.getElementById("stlMethod"),
      direction: document.getElementById("stlDirectionBadge"),
      entityId: document.getElementById("stlEntityId"),
      entityType: document.getElementById("stlEntityType"),
      confirm: document.getElementById("stlConfirm"),
      print: document.getElementById("stlPrint")
    };

    var balance = Number(payload.balance || 0);
    if (!isFinite(balance)) balance = 0;
    var amount = Math.abs(balance);
    var dir = balance > 0 ? "OUT" : (balance < 0 ? "IN" : "OUT");

    dom.name.textContent = payload.name || "";
    dom.balance.innerHTML = fmt(balance) + " " + (payload.currency || "");
    dom.amount.value = amount ? (Number.isInteger(amount) ? String(amount) : amount.toFixed(2)) : "";
    dom.amount.setAttribute("inputmode", "numeric");
    dom.amount.setAttribute("autocomplete", "off");
    dom.amount.setAttribute("dir", "ltr");
    dom.currency.value = String(payload.currency || "ILS").toUpperCase();
    dom.entityId.value = payload.id || "";
    dom.entityType.value = String(payload.entityType || "").toUpperCase();
    dom.direction.innerHTML = directionBadge(dir);
    dom.direction.dataset.dir = dir;
    dom.confirm.disabled = !(amount > 0);

    dom.amount.addEventListener("input", function () {
      var cur = dom.amount.value;
      var clean = sanitizeAmountInput(cur);
      if (clean !== cur) dom.amount.value = clean;
      dom.confirm.disabled = !(toNumber(dom.amount.value) > 0);
    });

    dom.amount.addEventListener("blur", function () {
      var n = toNumber(dom.amount.value);
      dom.amount.value = n ? (Number.isInteger(n) ? String(n) : n.toFixed(2)) : "";
    });

    if (dom.method) {
      showMethodSection(String(dom.method.value || "").toLowerCase());
      dom.method.addEventListener("change", function () {
        showMethodSection(String(dom.method.value || "").toLowerCase());
      }, { passive: true });
    }

    dom.confirm.onclick = function () {
      var cfg = document.getElementById("vendors-config");
      var base = (cfg && cfg.dataset && cfg.dataset.payUrl) ? cfg.dataset.payUrl : "/payments/create";
      var amountNum = toNumber(dom.amount.value);
      if (!(amountNum > 0)) return;

      var et = dom.entityType.value;
      var referenceBase = (et === "SUPPLIER") ? "SupplierSettle" : (et === "PARTNER" ? "PartnerSettle" : "Settlement");
      var noteText = (et === "SUPPLIER") ? "تسوية رصيد مورد" : (et === "PARTNER" ? "تسوية رصيد شريك" : "تسوية رصيد");

      var method = String(dom.method.value || "cash").toLowerCase();
      var params = new URLSearchParams({
        entity_type: et,
        entity_id: dom.entityId.value,
        direction: dom.direction.dataset.dir || dir,
        total_amount: amountNum.toString(),
        currency: dom.currency.value,
        method: method,
        reference: referenceBase,
        notes: noteText,
        status: "COMPLETED"
      });

      if (method === "cheque") {
        var cn = document.getElementById("mf_check_number")?.value || "";
        var cb = document.getElementById("mf_check_bank")?.value || "";
        var cd = document.getElementById("mf_check_due_date")?.value || "";
        if (cn) params.append("check_number", cn);
        if (cb) params.append("check_bank", cb);
        if (cd) params.append("check_due_date", cd);
      } else if (method === "bank") {
        var br = document.getElementById("mf_bank_transfer_ref")?.value || "";
        if (br) params.append("bank_transfer_ref", br);
      } else if (method === "card") {
        var ch = document.getElementById("mf_card_holder")?.value || "";
        var ce = document.getElementById("mf_card_expiry")?.value || "";
        var cc = (document.getElementById("mf_card_number")?.value || "").replace(/\D/g, "");
        if (ch) params.append("card_holder", ch);
        if (ce) params.append("card_expiry", ce);
        if (cc) params.append("card_number", cc);
      } else if (method === "online") {
        var og = document.getElementById("mf_online_gateway")?.value || "";
        var orf = document.getElementById("mf_online_ref")?.value || "";
        if (og) params.append("online_gateway", og);
        if (orf) params.append("online_ref", orf);
      }

      window.location.href = base + "?" + params.toString();
    };

    dom.print.onclick = function () {
      var w = window.open("", "printWin");
      var now = new Date().toLocaleString();
      var methodText = dom.method.options[dom.method.selectedIndex].text;
      var dirText = (dom.direction.dataset.dir || dir) === "IN" ? "وارد" : "صادر";
      var html =
        '<html dir="rtl"><head><meta charset="utf-8"><title>كشف تسوية</title>' +
        '<style>body{font-family:sans-serif;padding:20px} .row{margin:6px 0} .h{color:#666}</style>' +
        "</head><body>" +
        "<h3>كشف تسوية مختصر</h3>" +
        '<div class="row"><span class="h">الجهة:</span> ' + (payload.name || "") + "</div>" +
        '<div class="row"><span class="h">النوع:</span> ' + (dom.entityType.value === "PARTNER" ? "شريك" : "مورد") + "</div>" +
        '<div class="row"><span class="h">الرصيد الحالي:</span> ' + fmt(payload.balance) + " " + (payload.currency || "") + "</div>" +
        '<div class="row"><span class="h">المبلغ للتسوية:</span> ' + (dom.amount.value || "0") + " " + dom.currency.value + "</div>" +
        '<div class="row"><span class="h">الاتجاه:</span> ' + dirText + "</div>" +
        '<div class="row"><span class="h">الطريقة:</span> ' + methodText + "</div>" +
        "<hr><small>" + now + "</small>" +
        '<script>window.onload=function(){window.print();setTimeout(function(){window.close()},300)}</' + "script>" +
        "</body></html>";
      if (w && w.document) {
        w.document.write(html);
        w.document.close();
      }
    };

    if (bsModal) bsModal.show();
    else modalEl.style.display = "block";
  }

  function attachSettleButtons() {
    document.querySelectorAll(".btn-settle").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openSettlementModal({
          entityType: btn.dataset.entityType,
          id: btn.dataset.id,
          name: btn.dataset.name,
          balance: Number(btn.dataset.balance || 0),
          currency: btn.dataset.currency || "ILS"
        });
      });
    });
  }

  function wireSimpleSearch(inputId, tableId, selectors) {
    var input = document.getElementById(inputId);
    var table = document.getElementById(tableId);
    if (!input || !table || !table.tBodies.length) return;
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      Array.from(table.tBodies[0].rows).forEach(function (row) {
        var haystack = selectors.map(function (sel) {
          var el = row.querySelector(sel);
          return (el && el.textContent || "").toLowerCase();
        }).join(" ");
        row.style.display = haystack.includes(q) ? "" : "none";
      });
    });
  }

  function bindPrint() {
    var b = document.getElementById("btn-print");
    if (!b) return;
    b.addEventListener("click", function () { window.print(); });
  }

  document.addEventListener("DOMContentLoaded", function () {
    wireSimpleSearch("partnerSearch", "partnersTable", [".partner-name", ".partner-phone"]);
    wireSimpleSearch("supplierSearch", "suppliersTable", [".supplier-name", ".supplier-phone"]);
    attachSettleButtons();
    bindPrint();
    document.querySelectorAll("[data-bs-toggle=\"tooltip\"]").forEach(function (el) {
      if (window.bootstrap && bootstrap.Tooltip) new bootstrap.Tooltip(el);
    });
  });
})();
