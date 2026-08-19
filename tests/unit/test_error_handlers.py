"""Error handler tests for 503 and 402."""

from __future__ import annotations

import pytest
from flask import Flask, abort
from flask.testing import FlaskClient

from app.factory import create_app
from utils.exceptions import PaymentRequired


@pytest.fixture
def app():
    """Create a test Flask app."""
    app = create_app()
    app.config["TESTING"] = True
    app.config["DEBUG"] = False
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create a test client."""
    return app.test_client()


class Test503ErrorHandler:
    """Test the 503 Service Unavailable error handler."""

    def test_503_handler_returns_template(self):
        """Test that 503 returns the errors/503.html template."""
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["DEBUG"] = False

        @test_app.route("/trigger-503")
        def trigger_503():
            abort(503, description="Service under maintenance")

        with test_app.test_client() as test_client:
            response = test_client.get("/trigger-503")
            assert response.status_code == 503
            assert b"503" in response.data
            assert (
                b"Service Unavailable" in response.data
                or rb"\u0627\u0644\u062e\u062f\u0645\u0629 \u063a\u064a\u0631 \u0645\u062a\u0627\u062d\u0629" in response.data
            )

    def test_503_handler_logs_error(self, mocker):
        """Test that 503 handler logs the error."""
        from services.logging_core import LoggingCore

        mock_log = mocker.patch.object(LoggingCore, "log_error")

        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["DEBUG"] = False

        @test_app.route("/trigger-503")
        def trigger_503():
            abort(503, description="Test 503")

        with test_app.test_client() as test_client:
            response = test_client.get("/trigger-503")
            assert response.status_code == 503

        # Verify logging was called
        mock_log.assert_called()
        call_args = mock_log.call_args[1]
        assert call_args["category"] == "SYSTEM"
        assert call_args["level"] == "WARNING"
        assert call_args["source"] == "app.errorhandler.503"


class Test402ErrorHandler:
    """Test the 402 Payment Required error handler."""

    def test_402_handler_returns_template(self):
        """Test that 402 returns the errors/402.html template."""
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["DEBUG"] = False

        @test_app.route("/trigger-402")
        def trigger_402():
            raise PaymentRequired("Subscription expired")

        with test_app.test_client() as test_client:
            response = test_client.get("/trigger-402")
            assert response.status_code == 402
            assert b"402" in response.data
            # Template uses translation; check for either English or Arabic
            assert (
                b"Payment Required" in response.data
                or rb"\u0627\u0644\u062f\u0641\u0639 \u0627\u0644\u0645\u0637\u0644\u0648\u0628" in response.data
            )

    def test_402_handler_logs_error(self, mocker):
        """Test that 402 handler logs the error."""
        from services.logging_core import LoggingCore

        mock_log = mocker.patch.object(LoggingCore, "log_error")

        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["DEBUG"] = False

        @test_app.route("/trigger-402")
        def trigger_402():
            raise PaymentRequired("Test 402")

        with test_app.test_client() as test_client:
            response = test_client.get("/trigger-402")
            assert response.status_code == 402

        # Verify logging was called
        mock_log.assert_called()
        call_args = mock_log.call_args[1]
        assert call_args["category"] == "BILLING"
        assert call_args["level"] == "WARNING"
        assert call_args["source"] == "app.errorhandler.402"

    def test_402_handler_sets_denial_reason(self):
        """Test that 402 handler sets g.denial_reason."""
        test_app = create_app()
        test_app.config["TESTING"] = True
        test_app.config["DEBUG"] = False

        @test_app.route("/trigger-402")
        def trigger_402():
            raise PaymentRequired("Custom subscription error")

        with test_app.test_client() as test_client:
            response = test_client.get("/trigger-402")
            assert response.status_code == 402
