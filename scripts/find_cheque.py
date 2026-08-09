with open("routes/expenses.py", encoding="utf-8") as f:
    content = f.read()
for i, line in enumerate(content.split("\n"), 1):
    if "Cheque." in line:
        print(f"{i + 1}: {line.strip()}")
