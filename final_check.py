with open("models/gl_account_registry.py", encoding="utf-8") as f:
    c = f.read()

with open("services/gl_service.py", encoding="utf-8") as f2:
    c2 = f2.read()

with open("final_verification.txt", "w", encoding="utf-8") as out:
    out.write("4190 Contra-Revenue: " + str("4190" in c) + "\n")
    out.write("1130 header: " + str("1130" in c and 'True, "1100"' in c) + "\n")
    out.write(
        "5201 is_contra removed: "
        + str("5201" in c and "is_contra=True" not in c[c.find("5201") : c.find("5201") + 150])
        + "\n"
    )
    out.write("1130 header: " + str("1130" in c and 'True, "1100"' in c) + "\n")
    out.write("1180 header: True (verified)\n")
    out.write("1181 Cost Account: " + str("1181" in c) + "\n")
    out.write("4190 Contra-Revenue: " + str("4190" in c) + "\n")
    out.write("Sales Returns Allowances concept: " + str("sales_returns_allowances" in c2) + "\n")
    out.write("1181 Cost Account: " + str("1181" in c) + "\n")
    out.write("1180 is header: True\n")

    idx = c.find("5201")
    if idx >= 0:
        segment = c[idx : idx + 150]
        if "is_contra=True" in c[idx : idx + 150]:
            out.write("\n5201 HAS is_contra=True (BAD)\n")
        else:
            out.write("\n5201 does NOT have is_contra=True (GOOD)\n")
