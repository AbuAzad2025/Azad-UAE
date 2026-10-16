"""Phase 2: error governance for routes/payments.py.

The rule under test: an unexpected exception is a SYSTEM failure. Its trace is
logged; the page gets a calm sentence plus a reference, and never the database
message, the SQL, or the Python exception.
"""

import logging


class _CaptureHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class TestSystemErrorReporting:
    def test_reference_is_short_and_uppercase(self):
        from utils.error_messages import new_error_reference

        ref = new_error_reference()
        assert len(ref) == 8, f"a reference the user reads aloud should be short: {ref!r}"
        assert ref.isupper()

    def test_exception_text_never_reaches_the_returned_message(self):
        """The leak this whole layer exists to prevent."""
        from utils.error_messages import report_system_error

        leak = 'duplicate key value violates unique constraint "uq_sales_tenant_sale_number"'
        boom = RuntimeError(leak)

        logger = logging.getLogger("test.gov")
        handler = _CaptureHandler()
        logger.addHandler(handler)
        logger.propagate = False
        try:
            message = report_system_error(boom, context="delete payment 7", logger=logger)
        finally:
            logger.removeHandler(handler)

        assert leak not in message, f"raw database text leaked to the user: {message}"
        assert "RuntimeError" not in message
        assert "uq_sales_tenant_sale_number" not in message

    def test_the_message_is_actionable_and_carry_a_reference(self):
        from utils.error_messages import report_system_error

        logger = logging.getLogger("test.gov2")
        handler = _CaptureHandler()
        logger.addHandler(handler)
        logger.propagate = False
        try:
            message = report_system_error(ValueError("bad input"), context="archive", logger=logger)
        finally:
            logger.removeHandler(handler)

        reference = handler.records[-1].args[0]
        assert reference in message, "the user cannot quote the reference they were given"
        assert "المحاولة" in message or "الدعم" in message, (
            f"a system error must tell the user what to do next: {message}"
        )

    def test_the_trace_is_logged_with_the_context_and_reference(self):
        """If the trace is not logged, the reference is a dead end for support."""
        from utils.error_messages import report_system_error

        logger = logging.getLogger("test.gov3")
        handler = _CaptureHandler()
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.ERROR)
        try:
            report_system_error(RuntimeError("inner"), context="voucher submit incoming/customer", logger=logger)
        finally:
            logger.removeHandler(handler)

        record = handler.records[-1]
        assert record.levelno == logging.ERROR
        assert "voucher submit incoming/customer" in record.getMessage()
        assert record.exc_info is not None, "the traceback must reach the log, not just the message"
        assert record.exc_info[0] is RuntimeError

    def test_outside_an_app_context_it_still_works(self):
        """Reportable from a CLI, a worker or a test - not only inside a request."""
        from utils.error_messages import report_system_error

        message = report_system_error(OSError("disk"))
        assert message

    def test_business_helpers_are_not_classified_as_system(self):
        """The other half of the rule: guidance stays guidance, no crash noise."""
        from utils.error_messages import ErrorMessages

        business = ErrorMessages.payment_amount_zero()
        assert "0" not in business or "صفر" in business
        assert "رقم المرجع" not in business, "a business-rule message must not masquerade as a system failure"


class TestLeakingHelpersNoLongerLeak:
    def test_user_update_failed_drops_the_exception(self):
        from utils.error_messages import ErrorMessages

        secret = "psycopg2.errors.UniqueViolation on table public.users"
        message = ErrorMessages.user_update_failed(secret)
        assert secret not in message, "the raw exception is still rendered into the page"
        assert "psycopg2" not in message and "UniqueViolation" not in message

    def test_file_upload_failed_drops_the_exception(self):
        from utils.error_messages import ErrorMessages

        secret = "PermissionError: [Errno 13] /var/www/uploads"
        message = ErrorMessages.file_upload_failed(secret)
        assert secret not in message

    def test_both_stay_actionable(self):
        from utils.error_messages import ErrorMessages

        assert ErrorMessages.user_update_failed() and ErrorMessages.file_upload_failed()


class TestPaymentsRouteHasNoRawExceptionLeaks:
    def test_no_stray_exception_is_interpolated_into_a_flash(self):
        """Static guard: routes/payments.py used str(e) in six flashes."""
        from pathlib import Path

        source = Path("routes/payments.py").read_text(encoding="utf-8")
        offenders = [line.strip() for line in source.splitlines() if "flash(" in line and "str(e)" in line]
        assert not offenders, f"raw exception text still reaches the page: {offenders}"

    def test_no_stderr_or_traceback_printing_in_the_route(self):
        """These bypassed the configured handlers, so they never reached the sink."""
        from pathlib import Path

        # Comments are excluded on purpose: the fix documents what it removed, and
        # a static guard must not flag its own explanation.
        code = [
            line
            for line in Path("routes/payments.py").read_text(encoding="utf-8").splitlines()
            if not line.strip().startswith("#")
        ]
        source = "\n".join(code)
        for banned in ("sys.stderr.write", "traceback.print_exc()"):
            assert banned not in source, f"{banned} bypasses the logging configuration"

    def test_the_governed_paths_call_the_governance_helper(self):
        from pathlib import Path

        source = Path("routes/payments.py").read_text(encoding="utf-8")
        assert "report_system_error" in source, "the route must report system failures through the layer"
        assert source.count("report_system_error(") >= 6, "every former leak site should now go through the helper"


class TestGovernanceClassification:
    def test_categories_cover_the_documented_taxonomy(self):
        from utils.error_messages import ErrorCategory

        for name in ("SYSTEM", "BUSINESS", "VALIDATION", "SECURITY", "STATE"):
            assert hasattr(ErrorCategory, name), f"missing category: {name}"

    def test_a_system_message_is_distinguishable_from_business_guidance(self):
        from utils.error_messages import ErrorMessages

        system = ErrorMessages.unexpected_error("AB12CD34")
        business = ErrorMessages.payment_exceeds_due(150.0, 100.0)
        assert "رقم المرجع" in system
        assert "رقم المرجع" not in business
        assert system != business
