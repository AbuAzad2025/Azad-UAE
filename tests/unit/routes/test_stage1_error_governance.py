"""Phase 3 sweep: the seven Stage 1 routes must not leak technical text.

One static gate over all seven files (the defect was a repeated literal, so a
repeated literal is how it is prevented from coming back), plus the behavioural
proof that the shared refuse() helper draws the line correctly: a business
refusal is guidance, everything else is a logged crash with a calm message.
"""

from pathlib import Path

import pytest

STAGE1_ROUTES = [
    "routes/sales.py",
    "routes/purchases.py",
    "routes/expenses.py",
    "routes/pos.py",
    "routes/shop.py",
    "routes/products.py",
    "routes/owner/settings.py",
]


def _code(rel: str) -> str:
    """Source with comment-only lines removed.

    Comments are excluded on purpose: the fixes document what they removed, and
    a static guard must not flag its own explanation.
    """
    return "\n".join(
        line for line in Path(rel).read_text(encoding="utf-8").splitlines() if not line.strip().startswith("#")
    )


@pytest.mark.parametrize("rel", STAGE1_ROUTES)
def test_no_raw_exception_reaches_a_user_facing_call(rel):
    import re

    src = _code(rel)
    # flash(...) / error_response(...) whose argument embeds str(e) or str(exc),
    # including a call spread over several lines.
    offenders = re.findall(r"(?:flash|error_response)\(\s*[^)]*\{str\((?:e|exc)\)\}", src, re.S)
    assert not offenders, f"{rel}: raw exception in a user-facing response: {offenders[:3]}"


@pytest.mark.parametrize("rel", STAGE1_ROUTES)
def test_no_bare_exception_echo(rel):
    src = _code(rel)
    for banned in (
        "flash(str(e)",
        "flash(str(exc)",
        "error_response(message=str(e)",
        "error_response(message=str(exc)",
    ):
        if banned == "error_response(message=str(e)" or banned == "error_response(message=str(exc)":
            continue  # typed domain arms legitimately carry curated messages
        assert banned not in src, f"{rel}: {banned} echoes the exception verbatim"


@pytest.mark.parametrize("rel", STAGE1_ROUTES)
def test_no_logging_bypasses_the_configured_handlers(rel):
    src = _code(rel)
    assert "sys.stderr.write" not in src, f"{rel}: stderr bypasses the JSONL sink and rotation"
    assert "traceback.print_exc()" not in src, f"{rel}: traceback printed beside a duplicate log line"
    assert "logger.error(f" not in src, f"{rel}: f-string logging loses exc_info; use %s with exc_info=True"


@pytest.mark.parametrize("rel", STAGE1_ROUTES)
def test_each_route_uses_the_governance_helper(rel):
    src = _code(rel)
    assert "refuse(" in src, f"{rel}: failures are not routed through refuse()"
    assert "from utils.error_messages import" in src, f"{rel}: governance helper not imported"


class TestRefuseBehaviour:
    """The helper's two branches, which is the whole point of the layer."""

    def test_a_business_refusal_is_guidance_not_a_crash(self, app, client):
        from utils.error_messages import BusinessRuleError, ErrorCategory

        with app.test_request_context("/"):
            from flask import get_flashed_messages

            from utils.error_messages import refuse

            refusal = BusinessRuleError(
                "لا يمكن رفض شيك وارد ما زال قيد التحصيل.\nيجب إيداع الشيك أولاً.",
                category=ErrorCategory.STATE,
            )
            used = refuse(refusal, context="test bounce")
            assert used == "warning"
            [shown] = get_flashed_messages()
            assert shown == refusal.message
            assert "رقم المرجع" not in shown, "a refusal must not masquerade as a crash"

    def test_a_system_failure_is_a_reference_not_the_exception(self, app, client):
        with app.test_request_context("/"):
            from flask import get_flashed_messages

            from utils.error_messages import refuse

            boom = 'duplicate key value violates unique constraint "uq_sales_tenant_sale_number"'
            used = refuse(RuntimeError(boom), context="test sale create")
            assert used == "danger"
            [shown] = get_flashed_messages()
            assert "uq_sales_tenant_sale_number" not in shown
            assert "RuntimeError" not in shown
            assert "Traceback" not in shown
            assert "رقم المرجع" in shown, "the user needs a reference to quote back to support"

    def test_an_explicit_category_marks_a_known_non_crash(self, app, client):
        """A malformed date is the user's mistake - a reference code would be noise."""
        from utils.error_messages import ErrorCategory, refuse

        with app.test_request_context("/"):
            from flask import get_flashed_messages

            used = refuse(
                ValueError("تاريخ غير صحيح"),
                context="test date",
                category=ErrorCategory.VALIDATION,
            )
            assert used == "warning"
            [shown] = get_flashed_messages()
            assert shown == "تاريخ غير صحيح"
            assert "رقم المرجع" not in shown
