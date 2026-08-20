import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    s = f.read()

s = s.replace("“network”", '"network"')
s = s.replace("Promise.reject(new Error(“network”))", 'Promise.reject(new Error("network"))')

with open(path, "w", encoding="utf-8") as f:
    f.write(s)

print("Fixed")
