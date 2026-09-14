"""Gap100 for models/card_payment.py — ImportError fallback (lines 27-29).

Executes the real module top-level with ``cryptography.fernet`` blocked, so
the ``except ImportError`` branch runs against the genuine file/line numbers
(compiled with the real filename for coverage attribution). A stub ``db``
is injected to avoid re-registering the mapped ``CardPayment`` class.
"""

from __future__ import annotations

import builtins
import os
import sys
import types

CARD_PAYMENT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "models",
    "card_payment.py",
)


def _run_without_cryptography():
    with open(CARD_PAYMENT_PATH, encoding="utf-8") as fh:
        source = fh.read()

    real_import = builtins.__import__

    def _blocked_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "cryptography.fernet" or name.startswith("cryptography.fernet."):
            raise ImportError("No module named 'cryptography.fernet' (simulated)")
        return real_import(name, globals_, locals_, fromlist, level)

    class _DummyField:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return _DummyField()

    class _DummyDB:
        Model = object

        def __getattr__(self, item):
            return _DummyField

    fake_extensions = types.ModuleType("extensions")
    fake_extensions.db = _DummyDB()

    namespace = {"__name__": "models.card_payment_no_crypto_probe", "__builtins__": builtins}
    saved_extensions = sys.modules.get("extensions")
    saved_import = builtins.__import__
    sys.modules["extensions"] = fake_extensions
    builtins.__import__ = _blocked_import
    try:
        code = compile(source, CARD_PAYMENT_PATH, "exec")
        exec(code, namespace)
    finally:
        builtins.__import__ = saved_import
        if saved_extensions is None:
            sys.modules.pop("extensions", None)
        else:
            sys.modules["extensions"] = saved_extensions
    return namespace


class TestCryptographyMissingFallback:
    def test_except_import_error_branch_sets_stub(self):
        ns = _run_without_cryptography()
        assert ns["HAS_CRYPTO"] is False
        assert ns["Fernet"] is ns["_FernetStub"]

    def test_stub_from_fallback_still_raises(self):
        ns = _run_without_cryptography()
        stub_cls = ns["_FernetStub"]
        stub = stub_cls.__new__(stub_cls)
        try:
            stub.encrypt(b"data")
        except RuntimeError as exc:
            assert "cryptography module not installed" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
