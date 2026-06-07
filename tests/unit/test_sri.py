import hashlib, base64
from tools.generate_sri import sri_hash, find_cdn_urls, add_sri

class TestSriHash:
    def test_known_bootstrap_hash(self):
        h = sri_hash("https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css")
        assert h is not None
        assert h.startswith("sha384-")
        assert len(h) > 10
    def test_invalid_url_returns_none(self):
        h = sri_hash("https://invalid.example.com/nonexistent.css")
        assert h is None

class TestFindCdnUrls:
    def test_finds_jsdelivr(self):
        html = '<link href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css" rel="stylesheet">'
        urls = find_cdn_urls(html)
        assert "https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css" in urls
    def test_finds_cdnjs(self):
        html = '<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" rel="stylesheet">'
        urls = find_cdn_urls(html)
        assert "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css" in urls
    def test_finds_google_fonts(self):
        html = '<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap" rel="stylesheet">'
        urls = find_cdn_urls(html)
        assert len(urls) >= 1
    def test_skips_local(self):
        html = '<link href="/static/css/app.css" rel="stylesheet">'
        urls = find_cdn_urls(html)
        assert len(urls) == 0

class TestAddSri:
    def test_adds_to_link(self):
        html = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">'
        result = add_sri(html, "https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css", "sha384-test")
        assert 'integrity="sha384-test"' in result
        assert 'crossorigin="anonymous"' in result
    def test_adds_to_script(self):
        html = '<script src="https://cdn.jsdelivr.net/npm/jquery@3.6.4/dist/jquery.min.js"></script>'
        result = add_sri(html, "https://cdn.jsdelivr.net/npm/jquery@3.6.4/dist/jquery.min.js", "sha384-test")
        assert 'integrity="sha384-test"' in result
        assert 'crossorigin="anonymous"' in result
    def test_skips_if_already_present(self):
        html = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css" integrity="sha384-old">'
        result = add_sri(html, "https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css", "sha384-new")
        assert 'integrity="sha384-old"' in result
