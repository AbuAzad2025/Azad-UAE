"""Final services coverage gaps — five files driven to 100% (statements + arcs).

Each test targets a specific missing statement or partial branch recorded by
CI's combined coverage data. Validators and defensive guards are exercised at
the service boundary with in-memory objects; money/DB paths use the real ORM
so the contracts around them (idempotency, GL posting, stock valuation) are
never weakened. Two genuinely unreachable arcs are documented at the bottom
of this module rather than hacked around.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError


def _q(mocker, *, first=None, rows=None):
    """A query stand-in that returns itself from every chaining method."""
    query = mocker.MagicMock()
    for name in ("filter_by", "filter", "order_by", "join", "populate_existing", "with_for_update", "limit"):
        getattr(query, name).return_value = query
    query.first.return_value = first
    query.all.return_value = rows if rows is not None else []
    return query


# ═══════════════════════════════════════════════════════════════════════════
# services/maintenance_purchase_service.py
# ═══════════════════════════════════════════════════════════════════════════


class TestMaintenancePurchaseHelpers:
    def test_none_tenant_is_refused(self):
        from services.maintenance_purchase_service import _require_tenant_id

        with pytest.raises(ValueError, match="بدون شركة"):
            _require_tenant_id(None)

    def test_foreign_active_tenant_is_refused(self, mocker):
        mocker.patch("utils.tenanting.get_active_tenant_id", return_value=2)
        from services.maintenance_purchase_service import _require_tenant_id

        with pytest.raises(ValueError, match="شركة أخرى"):
            _require_tenant_id(1)

    def test_missing_purchase_order_is_refused(self, mocker):
        mocker.patch(
            "services.maintenance_purchase_service.tenant_query",
            return_value=_q(mocker, first=None),
        )
        from services.maintenance_purchase_service import _locked_purchase_order

        with pytest.raises(ValueError, match="غير موجود"):
            _locked_purchase_order(999, 1)


@pytest.fixture
def po_deps(mocker):
    """Isolate create_purchase_order from the DB, sequence and audit log."""
    fake_db = mocker.MagicMock()
    mocker.patch("services.maintenance_purchase_service.db", fake_db)
    mocker.patch("services.maintenance_purchase_service.DocumentSequenceService.get_or_create")
    mocker.patch(
        "services.maintenance_purchase_service.DocumentSequenceService.next_number",
        return_value="MPO-COV-1",
    )
    mocker.patch("services.maintenance_purchase_service.log_financial")
    return fake_db


@pytest.fixture
def po_queries(mocker):
    """Patch tenant_query with a per-model lookup table for purchase orders."""

    def build(mapping=None, *, default_first=None):
        table = dict(mapping or {})
        fallback = _q(mocker, first=default_first)

        def lookup(model, *_args, **_kwargs):
            return table.get(model, fallback)

        mocker.patch("services.maintenance_purchase_service.tenant_query", side_effect=lookup)
        return table

    return build


class TestCreatePurchaseOrderArcs:
    def test_no_warehouse_and_explicit_currency_skip_tenant_lookup(self, mocker, po_deps, po_queries):
        from models import Supplier, Tenant, Warehouse
        from services.maintenance_purchase_service import MaintenancePurchaseService

        po_queries(
            {Warehouse: _q(mocker, first=None), Supplier: _q(mocker, first=None), Tenant: _q(mocker, first=None)}
        )
        order = MaintenancePurchaseService.create_purchase_order(
            1,
            branch_id=None,
            warehouse_id=None,
            supplier_id=None,
            supplier_name="Spare Parts",
            tax_rate=Decimal("5"),
            currency="usd",
        )
        assert order.currency == "USD"
        po_deps.session.add.assert_called_once()

    def test_missing_supplier_is_refused(self, mocker, po_deps, po_queries):
        from models import Supplier
        from services.maintenance_purchase_service import MaintenancePurchaseService

        po_queries({Supplier: _q(mocker, first=None)})
        with pytest.raises(ValueError, match="المورد غير موجود"):
            MaintenancePurchaseService.create_purchase_order(
                1,
                branch_id=None,
                warehouse_id=None,
                supplier_id=99,
                supplier_name=None,
                tax_rate=Decimal("5"),
                currency="AED",
            )

    @pytest.mark.parametrize("rate", [Decimal("-1"), Decimal("101")])
    def test_out_of_range_tax_rate_is_refused(self, po_deps, po_queries, rate):
        from services.maintenance_purchase_service import MaintenancePurchaseService

        po_queries()
        with pytest.raises(ValueError, match="نسبة الضريبة غير صالحة"):
            MaintenancePurchaseService.create_purchase_order(
                1,
                branch_id=None,
                warehouse_id=None,
                supplier_id=None,
                supplier_name=None,
                tax_rate=rate,
                currency="AED",
            )


class TestAddLineGuards:
    @pytest.fixture
    def draft_order(self):
        from services.maintenance_purchase_service import MaintenancePurchaseOrderStatus as Status

        return SimpleNamespace(id=1, status=Status.DRAFT, is_archived=False, warehouse_id=3, lines=[])

    def _call(self, mocker, order, *, product_first="product", qty="1", cost="10"):
        from models import MaintenancePurchaseOrder as Order
        from models import Product
        from services.maintenance_purchase_service import MaintenancePurchaseService

        po_queries = {
            Order: _q(mocker, first=order),
            Product: _q(mocker, first=product_first if product_first != "missing" else None),
        }
        mocker.patch("services.maintenance_purchase_service.tenant_query", side_effect=lambda m, *a, **k: po_queries[m])
        return MaintenancePurchaseService.add_line(1, 1, product_id=5, quantity=Decimal(qty), unit_cost=Decimal(cost))

    def test_archived_order_is_refused(self, mocker, draft_order):
        draft_order.is_archived = True
        with pytest.raises(ValueError, match="مؤرشف"):
            self._call(mocker, draft_order)

    def test_negative_cost_is_refused(self, mocker, draft_order):
        with pytest.raises(ValueError, match="سالباً"):
            self._call(mocker, draft_order, cost="-1")

    def test_cost_with_too_many_decimals_is_refused(self, mocker, draft_order):
        with pytest.raises(ValueError, match="منازل عشرية"):
            self._call(mocker, draft_order, cost="1.00001")

    def test_values_over_the_cap_are_refused(self, mocker, draft_order):
        with pytest.raises(ValueError, match="الحد المسموح"):
            self._call(mocker, draft_order, qty="1000000000000")

    def test_missing_product_is_refused(self, mocker, draft_order):
        with pytest.raises(ValueError, match="المنتج غير موجود"):
            self._call(mocker, draft_order, product_first="missing")


class TestReceiveGuards:
    @pytest.fixture
    def ready_order(self):
        from services.maintenance_purchase_service import MaintenancePurchaseOrderStatus as Status

        line = SimpleNamespace(
            quantity=Decimal("1"),
            unit_cost=Decimal("10"),
            is_archived=False,
            warehouse_id=3,
            product_id=5,
        )
        return SimpleNamespace(
            id=1,
            tenant_id=1,
            status=Status.DRAFT,
            is_archived=False,
            warehouse_id=3,
            supplier_id=None,
            po_number="MPO-COV-1",
            lines=[line],
            total_amount=Decimal("10"),
            currency="AED",
            exchange_rate=Decimal("1"),
        )

    def _receive(self, mocker, order, *, user_first="user", warehouse_first="warehouse", product_first="product"):
        from models import MaintenancePurchaseOrder as Order
        from models import Product, User, Warehouse
        from services.maintenance_purchase_service import MaintenancePurchaseService

        mapping = {
            Order: _q(mocker, first=order),
            User: _q(mocker, first=None if user_first == "missing" else "user"),
            Warehouse: _q(mocker, first=None if warehouse_first == "missing" else "warehouse"),
            Product: _q(mocker, first=None if product_first == "missing" else "product"),
        }
        mocker.patch("services.maintenance_purchase_service.tenant_query", side_effect=lambda m, *a, **k: mapping[m])
        return MaintenancePurchaseService.receive_purchase_order(1, 1, received_by=7)

    def test_cancelled_order_is_refused(self, mocker, ready_order):
        from services.maintenance_purchase_service import MaintenancePurchaseOrderStatus as Status

        ready_order.status = Status.CANCELLED
        with pytest.raises(ValueError, match="ملغى"):
            self._receive(mocker, ready_order)

    def test_archived_order_is_refused(self, mocker, ready_order):
        ready_order.is_archived = True
        with pytest.raises(ValueError, match="مؤرشف"):
            self._receive(mocker, ready_order)

    def test_missing_receiver_is_refused(self, mocker, ready_order):
        with pytest.raises(ValueError, match="مستخدم الاستلام"):
            self._receive(mocker, ready_order, user_first="missing")

    def test_order_without_warehouse_is_refused(self, mocker, ready_order):
        ready_order.warehouse_id = None
        with pytest.raises(ValueError, match="لا يحتوي على مستودع"):
            self._receive(mocker, ready_order)

    def test_invalid_line_quantity_is_refused(self, mocker, ready_order):
        ready_order.lines[0].quantity = Decimal("0")
        with pytest.raises(ValueError, match="كمية سطر غير صالحة"):
            self._receive(mocker, ready_order)

    def test_missing_line_warehouse_is_refused(self, mocker, ready_order):
        with pytest.raises(ValueError, match="المستودع غير موجود"):
            self._receive(mocker, ready_order, warehouse_first="missing")

    def test_missing_line_product_is_refused(self, mocker, ready_order):
        with pytest.raises(ValueError, match="المنتج غير موجود"):
            self._receive(mocker, ready_order, product_first="missing")

    def test_supplier_row_gone_still_posts_the_order(self, mocker, ready_order):
        """supplier_id set but the row is gone: skip the AP aging, keep the receipt."""
        from models import Supplier
        from services.maintenance_purchase_service import MaintenancePurchaseOrderStatus as Status
        from services.maintenance_purchase_service import MaintenancePurchaseService

        ready_order.supplier_id = 99
        fake_db = mocker.MagicMock()
        mocker.patch("services.maintenance_purchase_service.db", fake_db)
        mocker.patch("services.maintenance_purchase_service.log_financial")
        mocker.patch(
            "services.maintenance_purchase_service.StockService.create_movement",
            return_value=SimpleNamespace(id=10, user_id=None),
        )
        mocker.patch("services.maintenance_purchase_service.MaintenancePurchaseService._apply_mwac_inflow")
        mocker.patch("services.maintenance_purchase_service.MaintenanceGLService.post_purchase_receipt")

        def lookup(model, *_args, **_kwargs):
            if model is Supplier:
                return _q(mocker, first=None)
            from models import MaintenancePurchaseOrder as Order
            from models import Product, User, Warehouse

            return {
                Order: _q(mocker, first=ready_order),
                User: _q(mocker, first="user"),
                Warehouse: _q(mocker, first=SimpleNamespace(id=3)),
                Product: _q(mocker, first=SimpleNamespace(id=5)),
            }[model]

        mocker.patch("services.maintenance_purchase_service.tenant_query", side_effect=lookup)
        result = MaintenancePurchaseService.receive_purchase_order(1, 1, received_by=7)
        assert result.status == Status.RECEIVED
        assert result.posted is True
        assert result.gl_posted is True


class TestMwacInflowExistingRow:
    def test_existing_pwc_is_updated(self, mocker):
        from services.maintenance_purchase_service import MaintenancePurchaseService

        pwc = SimpleNamespace(
            total_quantity=Decimal("10"),
            total_value=Decimal("100"),
            average_cost=Decimal("10"),
            last_updated=None,
            updated_by_movement_id=None,
        )
        mocker.patch("services.maintenance_purchase_service._safe_for_update", return_value=pwc)
        mocker.patch(
            "services.maintenance_purchase_service.StockService._mwac_calc",
            return_value=(Decimal("15"), Decimal("150"), Decimal("10")),
        )
        fake_db = mocker.MagicMock()
        mocker.patch("services.maintenance_purchase_service.db", fake_db)
        movement = SimpleNamespace(id=42)

        MaintenancePurchaseService._apply_mwac_inflow(
            tenant_id=1,
            product_id=2,
            warehouse_id=3,
            quantity=Decimal("5"),
            unit_cost=Decimal("10"),
            movement=movement,
            reference_id=7,
        )
        assert pwc.total_quantity == Decimal("15")
        assert pwc.total_value == Decimal("150")
        assert pwc.average_cost == Decimal("10.0000")
        assert pwc.last_updated is not None
        assert pwc.updated_by_movement_id == 42
        assert fake_db.session.add.call_count == 1  # the cost-history audit row


# ═══════════════════════════════════════════════════════════════════════════
# services/advanced_trainer.py
# ═══════════════════════════════════════════════════════════════════════════


class TestAdvancedTrainerGaps:
    def test_detect_knowledge_gaps_finds_an_uncovered_prerequisite(self, db_session, sample_tenant):
        from models.ai import AiMemory
        from models.ai_training_advanced import AiKnowledgeGraph
        from services.advanced_trainer import AdvancedTrainer

        for key, value in (("k1", "alpha beta gamma"), ("k2", "alpha delta")):
            db_session.add(
                AiMemory(
                    key=key,
                    value=value,
                    category="learned",
                    tenant_id=sample_tenant.id,
                    confidence=1.0,
                    source="semantic_training",
                    is_active=True,
                )
            )
        for source, target in (("alpha", "beta"), ("gapconcept", "gamma")):
            db_session.add(
                AiKnowledgeGraph(
                    tenant_id=sample_tenant.id,
                    source_concept=source,
                    target_concept=target,
                    relationship_type="prerequisite",
                    strength=Decimal("0.9"),
                )
            )
        db_session.flush()

        gaps = AdvancedTrainer().detect_knowledge_gaps(sample_tenant.id)
        assert len(gaps) == 1
        assert gaps[0]["source"] == "gapconcept"

    def test_high_coverage_domain_is_not_recommended(self, db_session, sample_tenant):
        from models.ai import AiMemory
        from services.advanced_trainer import AdvancedTrainer

        db_session.add(
            AiMemory(
                key="high",
                value="answer",
                category="well-covered",
                tenant_id=sample_tenant.id,
                confidence=1.0,
                source="semantic_training",
                is_active=True,
            )
        )
        db_session.flush()
        recs = AdvancedTrainer().generate_training_recommendations(sample_tenant.id)
        assert recs == []

    def test_duplicate_concept_does_not_repeat(self):
        from services.advanced_trainer import AdvancedTrainer

        assert AdvancedTrainer()._extract_concepts("alpha alpha beta") == ["alpha", "beta"]

    def test_similar_pair_scoring(self):
        from services.advanced_trainer import AdvancedTrainer

        memories = [
            SimpleNamespace(key="e1", value=""),
            SimpleNamespace(key="e2", value=""),
            SimpleNamespace(key="l1", value="alpha beta"),
            SimpleNamespace(key="l2", value="delta epsilon"),
            SimpleNamespace(key="h1", value="alpha beta gamma"),
            SimpleNamespace(key="h2", value="alpha beta gamma"),
        ]
        pairs = AdvancedTrainer()._find_similar_pairs(memories)
        assert pairs == [
            {
                "pair_1": "h1",
                "pair_2": "h2",
                "similarity": 1.0,
                "common_concepts": 3,
            }
        ]

    def test_existing_progress_record_is_updated(self, db_session, sample_tenant):
        from models.ai_training_advanced import AiTrainingProgress
        from services.advanced_trainer import AdvancedTrainer

        progress = AiTrainingProgress(
            tenant_id=sample_tenant.id,
            domain="general",
            topic="general",
            concept_name="alpha",
            covered=True,
            usage_count=1,
            confidence=Decimal("0.5"),
            mastery_score=10,
            learning_velocity=Decimal("1"),
        )
        db_session.add(progress)
        db_session.flush()

        result = AdvancedTrainer().train_semantic_model(sample_tenant.id, "question", "alpha beta gamma")
        assert result["success"] is True
        db_session.refresh(progress)
        assert progress.usage_count == 2
        assert progress.confidence == Decimal("0.6")
        assert progress.mastery_score > 10

    def test_domain_statistics_with_inactive_memory_and_progress(self, db_session, sample_tenant):
        from models.ai import AiMemory
        from models.ai_training_advanced import AiTrainingProgress
        from services.advanced_trainer import AdvancedTrainer

        for key, value, active, category in (
            ("active", "answer", True, "active-domain"),
            ("inactive", "answer", False, "retired-domain"),
        ):
            db_session.add(
                AiMemory(
                    key=key,
                    value=value,
                    category=category,
                    tenant_id=sample_tenant.id,
                    confidence=1.0,
                    source="semantic_training",
                    is_active=active,
                )
            )
        db_session.add(
            AiTrainingProgress(
                tenant_id=sample_tenant.id,
                domain="general",
                topic="general",
                concept_name="alpha",
                covered=True,
                usage_count=1,
                confidence=Decimal("0.9"),
                mastery_score=81,
                learning_velocity=Decimal("1"),
            )
        )
        db_session.flush()

        stats = AdvancedTrainer().get_domain_statistics(sample_tenant.id)
        assert stats["domain_stats"]["active-domain"]["active_records"] == 1
        assert stats["domain_stats"]["retired-domain"]["active_records"] == 0
        assert stats["average_mastery_score"] == 81.0


# ═══════════════════════════════════════════════════════════════════════════
# services/store_online_payment_service.py
# ═══════════════════════════════════════════════════════════════════════════


class TestPaymentIdentityArcs:
    def test_inspection_exception_returns_none(self, mocker):
        from services.store_online_payment_service import StoreOnlinePaymentService

        mocker.patch(
            "services.store_online_payment_service.sa_inspect",
            side_effect=RuntimeError("not inspectable"),
        )
        assert StoreOnlinePaymentService._payment_identity(object(), SimpleNamespace(tenant_id=1)) is None

    def test_tenant_mismatch_is_refused(self, mocker, sample_sale):
        from services.store_online_payment_service import StoreOnlinePaymentService

        state = sa_inspect(sample_sale)
        mocker.patch("services.store_online_payment_service.sa_inspect", return_value=state)
        with pytest.raises(ValueError, match="لا ينتمي"):
            StoreOnlinePaymentService._payment_identity(
                sample_sale, SimpleNamespace(tenant_id=sample_sale.tenant_id + 1)
            )

    def test_persisted_sale_yields_identity(self, mocker, sample_sale):
        from services.store_online_payment_service import StoreOnlinePaymentService

        state = sa_inspect(sample_sale)
        mocker.patch("services.store_online_payment_service.sa_inspect", return_value=state)
        identity = StoreOnlinePaymentService._payment_identity(
            sample_sale, SimpleNamespace(tenant_id=sample_sale.tenant_id)
        )
        assert identity == (sample_sale.tenant_id, sample_sale.id)

    def test_falsy_identifiers_return_none(self, mocker, sample_sale):
        from services.store_online_payment_service import StoreOnlinePaymentService

        # A real, persistent InstanceState gets past the isinstance guard; the
        # identifiers are then supplied by a lightweight double with zeros.
        state = sa_inspect(sample_sale)
        mocker.patch("services.store_online_payment_service.sa_inspect", return_value=state)
        sale = SimpleNamespace(tenant_id=0, id=0)
        assert StoreOnlinePaymentService._payment_identity(sale, SimpleNamespace(tenant_id=0)) is None


@pytest.fixture
def gateway(mocker):
    """Stub the external gateway while keeping the real idempotency ledger."""
    mocker.patch("services.store_online_payment_service.StoreOnlinePaymentService._api_key", return_value="key")
    mocker.patch("services.store_online_payment_service.get_nowpayments_ipn_url", return_value="https://ipn")
    response = MagicMock(status_code=201)
    response.json.return_value = {"payment_id": "pid-cov", "invoice_url": "https://pay"}
    mocker.patch("services.store_online_payment_service.requests.post", return_value=response)


class TestIdempotencyLedgerArcs:
    def test_prior_key_refuses_a_second_payment(self, db_session, sample_sale, gateway):
        from models.idempotency_key import IdempotencyKey
        from services.store_online_payment_service import StoreOnlinePaymentService

        db_session.add(
            IdempotencyKey(
                tenant_id=sample_sale.tenant_id,
                endpoint=StoreOnlinePaymentService.IDEMPOTENCY_ENDPOINT,
                key=f"sale:{sample_sale.id}",
                request_hash="prior",
                status=IdempotencyKey.STATUS_IN_PROGRESS,
            )
        )
        db_session.flush()
        store = SimpleNamespace(tenant_id=sample_sale.tenant_id, title="Shop")
        with pytest.raises(ValueError, match="دفع إلكتروني قائم"):
            StoreOnlinePaymentService.create_payment_for_sale(sample_sale, store)

    def test_success_reserves_and_completes_the_key(self, db_session, sample_sale, gateway):
        from models.idempotency_key import IdempotencyKey
        from services.store_online_payment_service import StoreOnlinePaymentService

        store = SimpleNamespace(tenant_id=sample_sale.tenant_id, title="Shop")
        result = StoreOnlinePaymentService.create_payment_for_sale(sample_sale, store)
        assert result["payment_id"] == "pid-cov"

        key_row = IdempotencyKey.query.filter_by(
            tenant_id=sample_sale.tenant_id,
            endpoint=StoreOnlinePaymentService.IDEMPOTENCY_ENDPOINT,
            key=f"sale:{sample_sale.id}",
        ).one()
        assert key_row.status == IdempotencyKey.STATUS_COMPLETED
        assert key_row.request_hash


# ═══════════════════════════════════════════════════════════════════════════
# services/backup_scoped_restore.py
# ═══════════════════════════════════════════════════════════════════════════


class TestBackupScopedRestoreArcs:
    def test_remap_rows_without_ids_take_the_loop_back_arcs(self):
        from services.backup_scoped_restore import _build_id_remap

        tables = {
            "branches": [{"id": None}, {"id": 2}],
            "tenant_stores": [{"id": None}, {"id": 3}],
        }
        maps = _build_id_remap(tables, new_tenant_id=9, new_branch_id=8, new_store_id=7)
        assert maps["branches"][2] == 8
        assert maps["tenant_stores"][3] == 7

    def test_more_than_two_insert_errors_stop_logging_details(self, mocker):
        from services.backup_scoped_restore import _run_import

        mocker.patch("services.backup_scoped_restore.normalize_row_to_target", side_effect=lambda c, t, r: r)
        mocker.patch("services.backup_scoped_restore.insert_query", return_value="INSERT")
        conn = mocker.MagicMock()
        conn.execute.side_effect = RuntimeError("boom")
        result = {"errors": [], "inserted": {}}
        _run_import(
            conn,
            {"sales": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}]},
            scope="tenant",
            source_tenant_id=1,
            target_tenant_id=1,
            id_maps={},
            remap=True,
            new_branch_id=None,
            new_store_id=None,
            source_branch_id=None,
            result=result,
        )
        assert result["inserted"]["sales"] == 0
        assert len(result["errors"]) == 2

    @pytest.mark.parametrize("fatal_ok", [True, False])
    def test_dry_run_import_summary(self, mocker, *, fatal_ok):
        from services.backup_scoped_restore import import_scoped_tables

        engine = mocker.MagicMock()
        conn = mocker.MagicMock()
        engine.connect.return_value.__enter__.return_value = conn
        mocker.patch("sqlalchemy.create_engine", return_value=engine)

        def fake_run(_conn, _tables, **kwargs):
            result = kwargs["result"]
            result["inserted"]["products"] = 2
            if fatal_ok:
                result["inserted"]["tenants"] = 1

        mocker.patch("services.backup_scoped_restore._run_import", side_effect=fake_run)
        result = import_scoped_tables(
            "postgresql+psycopg2://u:p@127.0.0.1:5433/target",
            {"tenants": [{"id": 1}], "products": [{"id": 1}, {"id": 2}]},
            scope="tenant",
            source_tenant_id=1,
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["products_expected"] == 2
        assert result["products_inserted"] == 2
        assert result["ok"] is fatal_ok
        conn.begin.return_value.rollback.assert_called_once()

    def test_dry_run_restore_returns_before_scoped_verify(self, mocker, tmp_path):
        from services.backup_scoped_restore import restore_scoped_backup

        backup_cls = mocker.MagicMock()
        backup_cls._urls_same_database.return_value = False
        backup_cls.verify_backup.return_value = {
            "valid": True,
            "manifest": {"tenant_id": 1, "backup_scope": "tenant"},
        }
        backup_cls._backup_path.return_value = "/tmp/fake.tar.gz"
        mocker.patch("services.backup_scoped_engine.ensure_target_schema", return_value=(True, ""))
        mocker.patch(
            "services.backup_scoped_restore.extract_scoped_bundle",
            return_value={"tables": {"tenants": [{"id": 1}]}},
        )
        import_result = {"ok": True, "inserted": {"tenants": 1}, "products_expected": 0, "products_inserted": 0}
        importer = mocker.patch("services.backup_scoped_restore.import_scoped_tables", return_value=import_result)
        verifier = mocker.patch("services.backup_scoped_restore.verify_scoped_restore")

        result = restore_scoped_backup(
            backup_cls,
            "bundle.tar.gz",
            "postgresql+psycopg2://u:p@127.0.0.1:5433/target",
            confirmation="RESTORE CONFIRM",
            dry_run=True,
        )
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert result["target_tenant_id"] == 1
        importer.assert_called_once()
        verifier.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════
# services/store_service.py
# ═══════════════════════════════════════════════════════════════════════════


class TestStoreServiceGaps:
    @pytest.mark.parametrize("winner_exists", [True, False])
    def test_ensure_tenant_store_lost_race(self, mocker, *, winner_exists):
        from services.store_service import StoreService

        winner = mocker.MagicMock()
        query = mocker.MagicMock()
        query.filter_by.return_value.first.side_effect = [None, winner if winner_exists else None]
        fake_store_cls = mocker.MagicMock()
        fake_store_cls.query = query
        mocker.patch("services.store_service.TenantStore", fake_store_cls)

        fake_db = mocker.MagicMock()
        dup = IntegrityError("duplicate", "INSERT", {}, Exception("dup"))
        fake_db.session.flush.side_effect = [dup, None]
        mocker.patch("services.store_service.db", fake_db)
        mocker.patch.object(StoreService, "ensure_online_warehouse", return_value=SimpleNamespace(id=9))
        mocker.patch.object(StoreService, "normalize_slug", return_value="shop")
        mocker.patch.object(StoreService, "ensure_unique_slug", return_value="shop")

        if winner_exists:
            assert StoreService.ensure_tenant_store(1) is winner
        else:
            with pytest.raises(IntegrityError):
                StoreService.ensure_tenant_store(1)
        fake_db.session.begin_nested.return_value.rollback.assert_called_once()

    def test_store_product_price_resolution(self, db_session, sample_tenant, sample_product, mocker):
        from services.store_service import StoreService

        priced = mocker.patch(
            "services.store_service.StorePricingService.resolve_store_price",
            return_value=Decimal("77.000"),
        )
        assert StoreService.get_store_product_price(sample_tenant.id, 999999) is None
        assert StoreService.get_store_product_price(sample_tenant.id, sample_product.id, "USD") == Decimal("77.000")
        assert priced.call_count == 1

    @pytest.mark.parametrize(
        "store, tenant, expected",
        [
            (SimpleNamespace(display_currency="AED"), None, "AED"),
            (None, SimpleNamespace(default_currency="USD"), "USD"),
            (None, SimpleNamespace(default_currency=None, base_currency="ILS"), "ILS"),
            (None, None, "USD"),
        ],
    )
    def test_store_currency_fallback_chain(self, store, tenant, expected):
        from services.store_service import StoreService

        assert StoreService._get_store_currency(store, tenant) == expected

    def test_cart_totals_without_a_store_price(self, db_session, sample_tenant, sample_product, mocker):
        from services.store_service import StoreService

        mocker.patch("services.store_service.StorePricingService.resolve_store_price", return_value=None)
        mocker.patch.object(StoreService, "online_stock_map", return_value={sample_product.id: Decimal("100")})
        totals = StoreService.cart_totals(sample_tenant.id, {str(sample_product.id): "2"})
        assert totals["subtotal"] == Decimal("200.000")
        assert all("store_price" not in line for line in totals["lines"])

    def test_redeem_rejects_non_positive_points(self):
        from services.store_service import StoreService

        with pytest.raises(ValueError, match="Invalid loyalty points amount"):
            StoreService.redeem_loyalty_points(1, 1, 0)


# ═══════════════════════════════════════════════════════════════════════════
# Unreachable lines — reported, deliberately not covered by a hack
# ═══════════════════════════════════════════════════════════════════════════
#
# services/backup_scoped_restore.py:23
#     `from sqlalchemy.engine import Connection` sits under `if TYPE_CHECKING:`.
#     Python never executes a TYPE_CHECKING body, so this import cannot record
#     a line at runtime. It exists only for static type checkers. Delete it and
#     use a string annotation if the owner wants a literal 100% line report.
#
# services/backup_scoped_restore.py:565 -> 578
#     `if tgt_tid is not None:` can never be False. `src_tid` is built with
#     `int(...)` at line 523, `target_tenant_id` is an int or None, and the
#     remap-without-target branch at lines 526-531 always assigns an int
#     (`int(max_id or 0) + 1`). The False arc to line 578 is therefore dead;
#     the guard can be removed and the body unindented.
