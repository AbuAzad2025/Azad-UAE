"""Bank import — statement parsing foundation, dedup, hash integrity."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock


class TestHashGeneration:
    """_generate_hash — deterministic dedup key."""

    def test_same_inputs_same_hash(self):
        from services.bank_import_service import BankImportService

        h1 = BankImportService._generate_hash(
            1, 5, date(2025, 6, 1), 100.0, "REF1", "desc"
        )
        h2 = BankImportService._generate_hash(
            1, 5, date(2025, 6, 1), 100.0, "REF1", "desc"
        )
        assert h1 == h2
        assert len(h1) == 64

    def test_tenant_change_alters_hash(self):
        from services.bank_import_service import BankImportService

        h1 = BankImportService._generate_hash(1, 5, date.today(), 50, "R", "d")
        h2 = BankImportService._generate_hash(2, 5, date.today(), 50, "R", "d")
        assert h1 != h2


class TestStatementImport:
    """import_bank_statement — duplicate block and DB commit."""

    def test_imports_new_line(self, app, mocker):
        from models.bank_reconciliation import BankStatementLine

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(
            BankStatementLine,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mock_session = mocker.patch("services.bank_import_service.db.session")

        from services.bank_import_service import BankImportService

        with app.app_context():
            lines = BankImportService.import_bank_statement(
                tenant_id=1,
                bank_account_id=10,
                user_id=3,
                filename="stmt.ofx",
                file_content=b"OFXDATA",
                fmt="ofx",
            )
        assert len(lines) == 1
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    def test_duplicate_reference_skipped(self, app, mocker):
        from models.bank_reconciliation import BankStatementLine

        existing = MagicMock(reference="test")
        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = existing
        mocker.patch.object(
            BankStatementLine,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mock_session = mocker.patch("services.bank_import_service.db.session")

        from services.bank_import_service import BankImportService

        with app.app_context():
            lines = BankImportService.import_bank_statement(
                1,
                10,
                3,
                "stmt.csv",
                b"data",
                format="csv",
            )
        assert lines == []
        mock_session.add.assert_not_called()

    def test_unrecognized_format_still_parses_placeholder(self, app, mocker):
        from models.bank_reconciliation import BankStatementLine

        mock_q = MagicMock()
        mock_q.filter_by.return_value.first.return_value = None
        mocker.patch.object(
            BankStatementLine,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=mock_q,
        )
        mocker.patch("services.bank_import_service.db.session")

        from services.bank_import_service import BankImportService

        with app.app_context():
            lines = BankImportService.import_bank_statement(
                1,
                10,
                3,
                "unknown.xlsx",
                b"excel-bytes",
                format="xlsx",
            )
        assert len(lines) == 1
        assert lines[0].status == "imported"


class TestMatchConfirmation:
    """confirm_match — missing line returns False safely."""

    def test_missing_line_returns_false(self, app, mocker):
        from models.bank_reconciliation import BankStatementLine

        mocker.patch.object(
            BankStatementLine,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=MagicMock(get=MagicMock(return_value=None)),
        )
        from services.bank_import_service import BankImportService

        with app.app_context():
            assert BankImportService.confirm_match(999, 1, 1) is False

    def test_confirm_match_success(self, app, mocker):
        from models.bank_reconciliation import BankStatementLine

        line = MagicMock(tenant_id=1, status="imported")
        mocker.patch.object(
            BankStatementLine,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=MagicMock(get=MagicMock(return_value=line)),
        )
        mock_session = mocker.patch("services.bank_import_service.db.session")
        from services.bank_import_service import BankImportService

        with app.app_context():
            assert BankImportService.confirm_match(1, 99, 7, tenant_id=1) is True
        assert line.status == "matched"
        mock_session.flush.assert_called_once()

    def test_confirm_match_cross_tenant_blocked(self, app, mocker):
        from models.bank_reconciliation import BankStatementLine

        line = MagicMock(tenant_id=2)
        mocker.patch.object(
            BankStatementLine,
            "query",
            new_callable=mocker.PropertyMock,
            return_value=MagicMock(get=MagicMock(return_value=line)),
        )
        from services.bank_import_service import BankImportService

        with app.app_context():
            assert BankImportService.confirm_match(1, 99, 7, tenant_id=1) is False

    def test_suggest_matches_noop(self):
        from services.bank_import_service import BankImportService

        assert BankImportService.suggest_matches(1, 2) is None
