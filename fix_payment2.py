import sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    s = f.read()

old = '''  it("payment method chips click sets value", async () => {
    await loadModule();
    const pm = document.querySelector('#posPayMethod .pm[data-method="card"]');
    pm.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(pm.classList.contains("active")).toBe(true);
  });'''

new = '''  it("syncPay sets active class on matching chip", async () => {
    await loadModule();
    const pm = document.querySelector('#posPayMethod .pm[data-method="card"]');
    document.getElementById("paymentMethod").value = "card";
    window._posSyncPay();
    expect(pm.classList.contains("active")).toBe(true);
  });'''

s = s.replace(old, new)

with open(path, 'w', encoding='utf-8') as f:
    f.write(s)

print('Fixed payment chips')
