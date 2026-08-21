"""Tests for utils.reporting_bind."""

from utils.reporting_bind import reporting_bind, use_reporting_bind


class TestReportingBind:
    def test_context_manager_runs_body(self, app):
        with app.app_context():
            with reporting_bind():
                assert True

    def test_decorator_runs_function(self, app):
        @use_reporting_bind()
        def fn():
            return "ok"

        with app.app_context():
            assert fn() == "ok"

    def test_unconfigured_bind_is_noop(self, app):
        """When reporting bind is not configured, body still executes."""
        with app.app_context():
            with reporting_bind("missing_bind"):
                assert True
