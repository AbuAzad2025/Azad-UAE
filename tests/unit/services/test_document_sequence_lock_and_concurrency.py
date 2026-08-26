"""DocumentSequenceService — row-lock retry ladder and real concurrency.

``_safe_for_update`` must retry ``SELECT … FOR UPDATE`` on transient lock
failures and ABORT (never silently fall back to an unlocked read) when
retries are exhausted.  A threaded barrier test then proves two interleaved
``next_number`` calls against PostgreSQL receive distinct consecutive
numbers.
"""

from __future__ import annotations

import contextlib
import threading
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError


def _lock_error():
    return OperationalError("SELECT", {}, Exception("could not obtain lock on row"))


def _fake_query(results):
    """Query stand-in whose with_for_update().first() pops from results."""
    query = MagicMock()
    query.with_for_update.return_value.first.side_effect = results
    return query


@pytest.fixture
def savepoint_mock(mocker):
    sp = MagicMock()
    mocker.patch("services.document_sequence_service.db.session.begin_nested", return_value=sp)
    return sp


@pytest.fixture
def app_logger_spy(mocker):
    spy = MagicMock()
    spy.__name__ = "spy_logger"
    mocker.patch("services.document_sequence_service.current_app", logger=spy)
    return spy


class TestSafeForUpdateRetryLadder:
    def test_returns_row_after_transient_failures(self, app, mocker, savepoint_mock, app_logger_spy):
        from services.document_sequence_service import _safe_for_update

        row = MagicMock(id=1)
        query = _fake_query([_lock_error(), _lock_error(), row])
        savepoint_mock.rollback.reset_mock()

        result = _safe_for_update(query, label="unit-test-row")

        assert result is row
        assert query.with_for_update.return_value.first.call_count == 3
        assert savepoint_mock.commit.call_count == 1
        assert savepoint_mock.rollback.call_count == 2
        assert app_logger_spy.warning.call_count == 2
        app_logger_spy.critical.assert_not_called()

    def test_aborts_after_max_retries(self, app, mocker, savepoint_mock, app_logger_spy):
        from services.document_sequence_service import _MAX_LOCK_RETRIES, _safe_for_update

        query = _fake_query([_lock_error() for _ in range(_MAX_LOCK_RETRIES)])

        with pytest.raises(OperationalError):
            _safe_for_update(query, label="doomed-row")

        assert query.with_for_update.return_value.first.call_count == _MAX_LOCK_RETRIES
        assert savepoint_mock.rollback.call_count == _MAX_LOCK_RETRIES
        app_logger_spy.critical.assert_called_once()

    def test_zero_retries_raises_runtime_guard(self, app, mocker, monkeypatch):
        """Defensive guard: a misconfigured retry budget must fail loudly."""
        from services import document_sequence_service as dss

        monkeypatch.setattr(dss, "_MAX_LOCK_RETRIES", 0)
        with pytest.raises(RuntimeError, match="Failed to acquire row lock"):
            dss._safe_for_update(_fake_query([]), label="never")


class TestNextNumberRealDatabase:
    def test_get_or_create_then_consecutive_numbers(self, db_session, sample_tenant):
        from services.document_sequence_service import DocumentSequenceService

        code = "sale"
        seq = DocumentSequenceService.get_or_create(sample_tenant.id, code)
        assert seq.prefix == "SALE"

        n1 = DocumentSequenceService.next_number(sample_tenant.id, code)
        n2 = DocumentSequenceService.next_number(sample_tenant.id, code)
        year = n1.split("-")[1]
        assert n1 == f"SALE-{year}-0001"
        assert n2 == f"SALE-{year}-0002"

    def test_inactive_sequence_rejected_before_locking(self, db_session, sample_tenant):
        from models.document_sequence import DocumentSequence
        from services.document_sequence_service import DocumentSequenceService

        code = f"covf_dead_{uuid.uuid4().hex[:6]}"
        DocumentSequenceService.get_or_create(sample_tenant.id, code)
        row = DocumentSequence.query.filter_by(tenant_id=sample_tenant.id, code=code).first()
        row.is_active = False
        db_session.flush()

        with pytest.raises(ValueError, match="inactive"):
            DocumentSequenceService.next_number(sample_tenant.id, code)

    def test_preview_does_not_consume_counter(self, db_session, sample_tenant):
        from services.document_sequence_service import DocumentSequenceService

        code = f"covf_prev_{uuid.uuid4().hex[:6]}"
        p1 = DocumentSequenceService.preview(sample_tenant.id, code)
        p2 = DocumentSequenceService.preview(sample_tenant.id, code)
        year = p1.split("-")[1]
        assert p1 == p2 == f"DOC-{year}-0001"


class TestConcurrentNumbering:
    """Two threads race through next_number behind a barrier — unique output."""

    @pytest.mark.parametrize("workers", [2, 4])
    def test_interleaved_calls_yield_unique_sequences(self, app, db_session, sample_tenant, workers):
        import sqlalchemy

        from extensions import db
        from services.document_sequence_service import DocumentSequenceService

        code = f"covf_race_{uuid.uuid4().hex[:6]}"
        DocumentSequenceService.get_or_create(sample_tenant.id, code)
        db.session.commit()

        barrier = threading.Barrier(workers, timeout=15)
        numbers: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker():
            try:
                with app.app_context():
                    # Fail fast instead of waiting forever if the row lock is
                    # never released (turns a potential deadlock into a
                    # recorded error the assertions can report).
                    db.session.execute(sqlalchemy.text("SET lock_timeout TO '8s'"))
                    barrier.wait()
                    number = DocumentSequenceService.next_number(sample_tenant.id, code)
                    db.session.commit()
                    with lock:
                        numbers.append(number)
            except Exception as exc:
                errors.append(exc)
                with contextlib.suppress(threading.BrokenBarrierError):
                    barrier.abort()
            finally:
                # Never leak a transaction holding the sequence row lock.
                with contextlib.suppress(Exception):
                    db.session.rollback()
                    db.session.remove()

        threads = [threading.Thread(target=worker, name=f"seq-{i}") for i in range(workers)]
        try:
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)
                assert not t.is_alive(), "sequence worker hung waiting for the row lock"
            assert errors == [], f"workers failed: {errors!r}"

            counters = sorted(int(n.rsplit("-", 1)[1]) for n in numbers)
            assert len(set(numbers)) == workers, f"duplicate numbers issued: {numbers}"
            assert counters == list(range(1, workers + 1))
        finally:
            # Force-release any pooled connection a crashed worker may hold.
            with contextlib.suppress(Exception):
                db.session.rollback()
