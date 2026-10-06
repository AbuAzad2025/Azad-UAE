import io, sys, pathlib, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
t = pathlib.Path("models/tenant.py").read_text(encoding="utf-8", errors="replace").split("\n")
for i,l in enumerate(t,1):
    if re.search(r"(slug|name)\s*=\s*db\.Column|name = Column|slug = Column", l) or re.search(r"unique=True", l) and i<80:
        print("%5d| %s" % (i, l.rstrip()[:92]))
