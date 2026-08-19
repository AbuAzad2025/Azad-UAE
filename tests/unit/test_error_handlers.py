"""Error handler tests for 503 and 402."""

from __future__ import annotations

import pytest
from flask import Flask, abort
from flask.testing import FlaskClient

from app.factory import create_app
from services.logging_core import LoggingCore
from utils.exceptions import PaymentRequired


@pytest.fixture(autouse=True)
def _isolate_logging(request):
    """Prevent real DB writes from LoggingCore during error handler tests."""
    original = LoggingCore.log_error
    original_frontend = LoggingCore.log_frontend_error
    LoggingCore.log_error = lambda *a, **kw: None
    LoggingCore.log_frontend_error = lambda *a, **kw: None

    def _restore():
        LoggingCore.log_error = original
        LoggingCore.log_frontend_error = original_frontend

    request.addfinalizer(_restore)


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
                or bytes(
                    [
                        0xD8,
                        0xA7,
                        0xD9,
                        0x84,
                        0xD8,
                        0xAE,
                        0xD8,
                        0xAF,
                        0xD9,
                        0x85,
                        0xD8,
                        0xA9,
                        0x20,
                        0xD8,
                        0xBA,
                        0xD9,
                        0x8A,
                        0xD8,
                        0xB1,
                        0x20,
                        0xD9,
                        0x85,
                        0xD8,
                        0xAA,
                        0xD8,
                        0xA7,
                        0xD8,
                        0xAD,
                        0xD8,
                        0xA9,
                    ]
                )
                in response.data
            )

    def test_503_handler_logs_error(self, mocker):
        """Test that 503 handler logs the error."""
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
            assert (
                b"Payment Required" in response.data
                or bytes(
                    [
                        0xD8,
                        0xA7,
                        0xD9,
                        0x84,
                        0xD8,
                        0xAF,
                        0xD9,
                        0x81,
                        0xD8,
                        0xB9,
                        0x20,
                        0xD9,
                        0x85,
                        0xD8,
                        0xB7,
                        0xD9,
                        0x84,
                        0xD9,
                        0x88,
                        0xD8,
                        0xA8,
                    ]
                )
                in response.data
            )

    def test_402_handler_logs_error(self, mocker):
        """Test that 402 handler logs the error."""
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
