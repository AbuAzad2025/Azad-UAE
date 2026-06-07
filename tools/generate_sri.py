import hashlib
import base64
import re
import os
import urllib.request
from pathlib import Path

def sri_hash(url):
    try:
        data = urllib.request.urlopen(url, timeout=15).read()
        h = hashlib.sha384(data).digest()
        return "sha384-" + base64.b64encode(h).decode()
    except Exception as e:
        print(f"ERROR {url}: {e}")
        return None

def find_cdn_urls(content):
    pattern = r'(?:href|src)=["\'](https://(?:cdn\.jsdelivr|cdnjs\.cloudflare|fonts\.googleapis)[^"\']+)["\']'
    return set(re.findall(pattern, content))

def add_sri(content, url, integrity):
    for attr in ("href", "src"):
        old = f'{attr}="{url}"'
        if old in content and "integrity=" not in content.split(old)[0].split(">")[-1]:
            new = f'{attr}="{url}" integrity="{integrity}" crossorigin="anonymous"'
            content = content.replace(old, new)
    return content

def process_templates(templates_dir):
    cache = {}
    for path in Path(templates_dir).rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        urls = find_cdn_urls(text)
        if not urls:
            continue
        changed = False
        for url in urls:
            if url not in cache:
                cache[url] = sri_hash(url)
            integrity = cache[url]
            if integrity and f'integrity="{integrity}"' not in text:
                text = add_sri(text, url, integrity)
                changed = True
        if changed:
            path.write_text(text, encoding="utf-8")
            print(f"Updated {path}")

if __name__ == "__main__":
    process_templates("templates")
