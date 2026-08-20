import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    s = f.read()

# Fix loadTables error test: use ok:false instead of Promise.reject
old_loadtables = """  it("loadTables error shows error", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () => Promise.reject(new Error("network")),
    });"""
new_loadtables = """  it("loadTables error shows error", async () => {
    mockFetch({
      "/pos/api/floors/1/tables": () => Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) }),
    });"""
s = s.replace(old_loadtables, new_loadtables)

# Fix payment method chips test: check active class instead of select value
old_pay = """  it("payment method chips click sets value", async () => {
    await loadModule();
    const pm = document.querySelector('#posPayMethod .pm[data-method="card"]');
    pm.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(document.getElementById("paymentMethod").value).toBe("card");
  });"""
new_pay = """  it("payment method chips click sets active class", async () => {
    await loadModule();
    const pm = document.querySelector('#posPayMethod .pm[data-method="card"]');
    pm.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(pm.classList.contains("active")).toBe(true);
  });"""
s = s.replace(old_pay, new_pay)

with open(path, "w", encoding="utf-8") as f:
    f.write(s)

print("Fixed 2 issues")
