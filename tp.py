import pathlib
p = pathlib.Path("tests/integration/business_scenarios/test_wave4_purchasing.py")
t = p.read_text(encoding="utf-8", errors="replace")
# The route is warehouse_bp("/transfer") under a /warehouse prefix, so there is
# no /api/ segment; a guessed path returns the HTML 404 page, not an error.
t = t.replace('"/warehouse/api/transfer"', '"/warehouse/transfer"')
p.write_text(t, encoding="utf-8", newline="\n")
print("  transfer path corrected to /warehouse/transfer")
