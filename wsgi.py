"""Production WSGI entrypoint (gunicorn target: ``wsgi:app``).

Reuses the canonical boot path in ``app.py`` so the served application is
identical to ``python app.py`` and to what the ``verify-boot`` CI job checks.
Referenced by: Dockerfile.ci CMD, e2e-tours and lighthouse-ci CI jobs.
"""

from app import app

__all__ = ["app"]
