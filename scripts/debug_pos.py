f = open('static/js/pos/index.js', 'r', encoding='utf-8')
c = f.read()
f.close()
old = 'const res = await fetchJson("/pos/api/categories");'
new = 'const res = await fetchJson("/pos/api/categories"); console.log("LC res", res);'
c = c.replace(old, new)
old2 = 'const cats = res.data;'
new2 = 'const cats = res.data; console.log("LC cats", cats, typeof cats, Array.isArray(cats));'
c = c.replace(old2, new2, 1)
f = open('static/js/pos/index.js', 'w', encoding='utf-8')
f.write(c)
f.close()
print('done')
