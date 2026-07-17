from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from utils import telemetry as telemetry_module
from utils.telemetry import (
    collect_system_info,
    get_machine_signature,
    get_reporting_url,
    has_reported_before,
    mark_as_reported,
    save_local_log,
    send_formsubmit,
    send_heartbeat,
    start_telemetry,
)


class TestReportingUrl:
    def test_prefers_env_url(self, monkeypatch):
        monkeypatch.setenv("FORM_SUBMIT_URL", "https://example.com/report")
        assert get_reporting_url() == "https://example.com/report"

    def test_builds_url_from_email_sources(self, monkeypatch):
        monkeypatch.delenv("FORM_SUBMIT_URL", raising=False)
        monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
        assert get_reporting_url() == "https://formsubmit.co/owner@example.com"

    def test_returns_default_without_email(self, monkeypatch):
        monkeypatch.delenv("FORM_SUBMIT_URL", raising=False)
        monkeypatch.delenv("FORM_SUBMIT_EMAIL", raising=False)
        monkeypatch.delenv("OWNER_EMAIL", raising=False)
        monkeypatch.delenv("COMPANY_EMAIL", raising=False)
        assert get_reporting_url() == "https://formsubmit.co"


class TestMachineSignature:
    def test_builds_signature_from_platform(self):
        with (
            patch("utils.telemetry.socket.gethostname", return_value="host"),
            patch("utils.telemetry.platform.machine", return_value="x86"),
            patch("utils.telemetry.platform.processor", return_value="intel"),
            patch("utils.telemetry.platform.node", return_value="node1"),
        ):
            assert get_machine_signature() == "host|x86|intel|node1"

    def test_returns_unknown_on_error(self):
        with patch("utils.telemetry.socket.gethostname", side_effect=OSError("fail")):
            assert get_machine_signature() == "unknown_machine"


class TestTokenFileHelpers:
    def test_has_reported_before_paths(self, tmp_path, monkeypatch):
        token_file = tmp_path / "instance" / ".machine_token"
        monkeypatch.setattr(telemetry_module, "TOKEN_FILE", str(token_file))
        assert has_reported_before("sig-a") is False
        token_file.parent.mkdir(parents=True)
        token_file.write_text("sig-a", encoding="utf-8")
        assert has_reported_before("sig-a") is True
        assert has_reported_before("sig-b") is False

    def test_has_reported_before_handles_read_errors(self, monkeypatch):
        monkeypatch.setattr(telemetry_module, "TOKEN_FILE", "/missing/path/token")
        with (
            patch("utils.telemetry.os.path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("read fail")),
        ):
            assert has_reported_before("sig") is False

    def test_mark_as_reported_writes_signature(self, tmp_path, monkeypatch):
        token_file = tmp_path / "instance" / ".machine_token"
        monkeypatch.setattr(telemetry_module, "TOKEN_FILE", str(token_file))
        mark_as_reported("machine-sig")
        assert token_file.read_text(encoding="utf-8") == "machine-sig"

    def test_mark_as_reported_swallows_write_errors(self, monkeypatch):
        with patch("builtins.open", side_effect=OSError("write fail")):
            mark_as_reported("sig")


class TestCollectSystemInfo:
    def test_collects_info_with_primary_ip_service(self, monkeypatch):
        monkeypatch.setattr(
            telemetry_module.requests,
            "get",
            MagicMock(return_value=MagicMock(json=lambda: {"ip": "203.0.113.10"})),
        )
        with (
            patch("utils.telemetry.socket.gethostname", return_value="srv"),
            patch("utils.telemetry.platform.system", return_value="Windows"),
            patch("utils.telemetry.platform.release", return_value="11"),
            patch("utils.telemetry.platform.machine", return_value="AMD64"),
            patch("utils.telemetry.platform.processor", return_value="cpu"),
            patch("utils.telemetry.platform.python_version", return_value="3.12.0"),
        ):
            info = collect_system_info()
        assert info["hostname"] == "srv"
        assert info["public_ip"] == "203.0.113.10"

    def test_falls_back_to_secondary_ip_service(self, monkeypatch):
        secondary = MagicMock()
        secondary.json.return_value = {"ip_addr": "198.51.100.4"}
        monkeypatch.setattr(
            telemetry_module.requests,
            "get",
            MagicMock(side_effect=[RuntimeError("down"), secondary]),
        )
        with (
            patch("utils.telemetry.socket.gethostname", return_value="srv"),
            patch("utils.telemetry.platform.system", return_value="Linux"),
            patch("utils.telemetry.platform.release", return_value="6"),
            patch("utils.telemetry.platform.machine", return_value="x86_64"),
            patch("utils.telemetry.platform.processor", return_value="cpu"),
            patch("utils.telemetry.platform.python_version", return_value="3.12.0"),
        ):
            info = collect_system_info()
        assert info["public_ip"] == "198.51.100.4"

    def test_returns_error_payload_on_failure(self):
        with patch(
            "utils.telemetry.socket.gethostname", side_effect=RuntimeError("boom")
        ):
            assert collect_system_info()["error"] == "boom"

    def test_keeps_unknown_ip_when_all_services_fail(self, monkeypatch):
        monkeypatch.setattr(
            telemetry_module.requests, "get", MagicMock(side_effect=RuntimeError("net"))
        )
        with (
            patch("utils.telemetry.socket.gethostname", return_value="srv"),
            patch("utils.telemetry.platform.system", return_value="Linux"),
            patch("utils.telemetry.platform.release", return_value="6"),
            patch("utils.telemetry.platform.machine", return_value="x86_64"),
            patch("utils.telemetry.platform.processor", return_value="cpu"),
            patch("utils.telemetry.platform.python_version", return_value="3.12.0"),
        ):
            info = collect_system_info()
        assert info["public_ip"] == "Unknown"


class TestLocalLogAndSubmit:
    def test_save_local_log_appends_json_line(self, tmp_path, monkeypatch):
        log_file = tmp_path / "instance" / ".security_audit.log"
        monkeypatch.setattr(telemetry_module, "HIDDEN_LOG_FILE", str(log_file))
        save_local_log({"event": "boot"})
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert json.loads(lines[0])["event"] == "boot"

    def test_save_local_log_swallows_write_errors(self, monkeypatch):
        with patch("builtins.open", side_effect=OSError("denied")):
            save_local_log({"event": "boot"})

    def test_send_formsubmit_success_and_failure(self, monkeypatch):
        ok_response = MagicMock(status_code=200)
        monkeypatch.setattr(
            telemetry_module.requests, "post", MagicMock(return_value=ok_response)
        )
        assert (
            send_formsubmit("subject", {"k": "v"}, to_email="ops@example.com") is True
        )
        monkeypatch.setattr(
            telemetry_module.requests,
            "post",
            MagicMock(side_effect=RuntimeError("net")),
        )
        assert send_formsubmit("subject", {"k": "v"}) is False


class TestHeartbeatAndStart:
    def test_send_heartbeat_skips_when_already_reported(self, monkeypatch):
        monkeypatch.setattr(telemetry_module, "get_machine_signature", lambda: "sig")
        monkeypatch.setattr(telemetry_module, "has_reported_before", lambda sig: True)
        with (
            patch("utils.telemetry.collect_system_info") as collect,
            patch("utils.telemetry.send_formsubmit") as submit,
        ):
            send_heartbeat()
        collect.assert_not_called()
        submit.assert_not_called()

    def test_send_heartbeat_first_run_marks_success(self, monkeypatch):
        monkeypatch.setattr(
            telemetry_module, "get_machine_signature", lambda: "sig-new"
        )
        monkeypatch.setattr(telemetry_module, "has_reported_before", lambda sig: False)
        monkeypatch.setattr(
            telemetry_module,
            "collect_system_info",
            lambda: {
                "timestamp": "2026-01-01T00:00:00",
                "hostname": "pc",
                "public_ip": "1.1.1.1",
                "os": "Windows",
                "os_release": "11",
                "processor": "cpu",
            },
        )
        with (
            patch("utils.telemetry.save_local_log") as save_log,
            patch("utils.telemetry.send_formsubmit", return_value=True) as submit,
            patch("utils.telemetry.mark_as_reported") as mark,
        ):
            send_heartbeat()
        save_log.assert_called_once()
        submit.assert_called_once()
        mark.assert_called_once_with("sig-new")

    def test_send_heartbeat_swallows_errors(self, monkeypatch):
        def boom():
            raise RuntimeError("x")

        monkeypatch.setattr(telemetry_module, "get_machine_signature", boom)
        send_heartbeat()

    def test_start_telemetry_disabled_and_enabled(self, monkeypatch):
        monkeypatch.setenv("DISABLE_TELEMETRY", "true")
        with patch("utils.telemetry.Thread") as thread_cls:
            start_telemetry()
        thread_cls.assert_not_called()

        monkeypatch.setenv("DISABLE_TELEMETRY", "false")
        thread = MagicMock()
        thread_cls.return_value = thread
        with patch("utils.telemetry.Thread", thread_cls):
            start_telemetry()
        thread.start.assert_called_once()
        assert thread.daemon is True
