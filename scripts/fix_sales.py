with open('static/js/sales.js', encoding='utf-8') as f:
    content = f.read()

# Find the closing of initForm and the outer IIFE
old = """\t\tbindAll();
\t\tif (addBtn) on(addBtn, "click", addLine);
\t\tconst taxRate = qs("#taxRate");
\t\tif (taxRate) on(taxRate, "input", recalcDebounced);
\t\tconst shipping = qs("#shippingCost");
\t\tif (shipping) on(shipping, "input", recalcDebounced);
\t\tconst currency = qs('select[name="currency"]');
\t\tif (currency) on(currency, "change", recalcDebounced);
\t\trecalc();
\t})();
})();"""

new = """\t\tbindAll();
\t\tif (addBtn) on(addBtn, "click", addLine);
\t\tconst taxRate = qs("#taxRate");
\t\tif (taxRate) on(taxRate, "input", recalcDebounced);
\t\tconst shipping = qs("#shippingCost");
\t\tif (shipping) on(shipping, "input", recalcDebounced);
\t\tconst currency = qs('select[name="currency"]');
\t\tif (currency) on(currency, "change", recalcDebounced);
\t\trecalc();

\t\t// Expose key functions for testability
\t\twindow._salesAddLine = addLine;
\t\twindow._salesRemoveLine = removeLine;
\t\twindow._salesRecalc = recalc;
\t\twindow._salesClearRow = clearRow;
\t\twindow._salesRenumberRow = renumberRow;
\t\twindow._salesCurrentMaxIndex = currentMaxIndex;
\t\twindow._salesFetchProductInfo = fetchProductInfo;
\t\twindow._salesUpdateAvailability = updateAvailability;
\t})();
})();"""

if old not in content:
    print("Old string not found")
    # Print last 500 chars to debug
    print(repr(content[-500:]))
    exit(1)

content = content.replace(old, new)

with open('static/js/sales.js', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
