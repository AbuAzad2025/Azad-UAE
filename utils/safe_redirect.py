"""Safe redirect helpers — prevent open redirects."""

from urllib.parse import urlparse

from flask import url_for


def is_safe_redirect_url(url: str | None) -> bool:
    """Allow same-app relative paths only (reject protocol-relative and off-site URLs)."""
    if not url:
        return False
    url = url.strip()
    if not url.startswith("/") or url.startswith("//"):
        return False
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return False
    return True


def safe_redirect_target(
    url: str | None, default_endpoint: str = "main.dashboard", **url_kwargs
):
    """Return a safe redirect target URL or url_for(default)."""
    if is_safe_redirect_url(url):
        return url
    return url_for(default_endpoint, **url_kwargs)
