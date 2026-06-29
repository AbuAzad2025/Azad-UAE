import hashlib
import gzip
import os
import shutil

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _minify_js(text):
    try:
        import jsmin
        return jsmin.jsmin(text)
    except ImportError:
        return None


def _minify_css(text):
    try:
        import cssmin
        return cssmin.cssmin(text)
    except ImportError:
        try:
            import rcssmin
            return rcssmin.cssmin(text)
        except ImportError:
            return None


def _minify(text, ext):
    if ext == '.js':
        return _minify_js(text)
    return _minify_css(text)


def _gzip_file(src_path):
    gz_path = src_path + '.gz'
    with open(src_path, 'rb') as f_in:
        with gzip.open(gz_path, 'wb', compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)
    return gz_path


def _process_file(src_path):
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in ('.js', '.css'):
        return None
    dir_name = os.path.dirname(src_path)
    base_name = os.path.basename(src_path)
    stem = os.path.splitext(base_name)[0]
    with open(src_path, 'r', encoding='utf-8') as f:
        original = f.read()
    minified_bytes = _minify(original, ext)
    hash_min_name = f"{stem}.min{ext}"
    min_name = f"{stem}.min{ext}"
    hash_min_path = os.path.join(dir_name, hash_min_name)
    min_path = os.path.join(dir_name, min_name)
    if minified_bytes is None:
        shutil.copy2(src_path, min_path)
        final_content = original.encode('utf-8')
    else:
        with open(min_path, 'w', encoding='utf-8') as f:
            f.write(minified_bytes)
        final_content = minified_bytes.encode('utf-8') if isinstance(minified_bytes, str) else minified_bytes
    digest = hashlib.md5(final_content, usedforsecurity=False).hexdigest()[:12]
    hash_name = f"{stem}.{digest}.min{ext}"
    hash_path = os.path.join(dir_name, hash_name)
    if minified_bytes is None:
        shutil.copy2(src_path, hash_path)
    else:
        with open(hash_path, 'w', encoding='utf-8') as f:
            f.write(minified_bytes if isinstance(minified_bytes, str) else minified_bytes.decode('utf-8'))
    gz_path = _gzip_file(hash_path)
    return {
        'file': base_name,
        'original': len(original),
        'minified': len(final_content),
        'gzipped': os.path.getsize(gz_path),
        'hash': digest,
    }


def _collect_files(base_dir, sub_dir, extensions):
    target = os.path.join(base_dir, sub_dir)
    if not os.path.isdir(target):
        return []
    result = []
    for entry in os.listdir(target):
        if any(entry.endswith(e) for e in extensions):
            if entry.endswith('.min.js') or entry.endswith('.min.css'):
                continue
            result.append(os.path.join(target, entry))
    return sorted(result)


def build_all(base_dir=None):
    if base_dir is None:
        base_dir = BASE
    results = []
    js_files = _collect_files(base_dir, 'static/js', ('.js',))
    css_files = _collect_files(base_dir, 'static/css', ('.css',))
    all_files = js_files + css_files
    for src in all_files:
        info = _process_file(src)
        if info:
            results.append(info)
            ext = os.path.splitext(info['file'])[1].upper()[1:]
            print(f"  {ext} {info['file']}: {info['original']:>8}B -> {info['minified']:>8}B -> {info['gzipped']:>8}B.gz  [{info['hash']}]")
    total_orig = sum(r['original'] for r in results)
    total_gz = sum(r['gzipped'] for r in results)
    saved = total_orig - total_gz
    pct = (saved / total_orig * 100) if total_orig else 0
    print()
    print(f"  Processed {len(results)} files")
    print(f"  Original:  {total_orig:>10}B")
    print(f"  Gzipped:   {total_gz:>10}B")
    print(f"  Saved:     {saved:>10}B ({pct:.1f}%)")
    return results
