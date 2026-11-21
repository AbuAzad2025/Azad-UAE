"""Coverage gaps across utils/ and a handful of small model branches.

These are the lines the main slices leave behind: defensive guards, late
imports, and small data helpers.  The tests are intentionally narrow - one
behaviour per test - so a failure names the exact branch that rotted.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from utils import seed_manifest as manifest
from utils import tenant_limits as tl
from utils.numeric_input import parse_decimal_field, parse_float_field, parse_int_field


class TestNumericInputRemainingBranches:
    """utils/numeric_input.py - the strict-parsing error paths."""

    def test_decimal_instance_is_accepted(self):
        value = Decimal("12.500")
        assert parse_decimal_field(value) is value

    def test_non_finite_decimal_is_rejected(self):
        for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with pytest.raises(ValueError, match="must be a number"):
                parse_decimal_field(bad, field="tax_rate")

    def test_negative_rejected_when_not_allowed(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            parse_decimal_field("-1", allow_negative=False, field="customs")

    def test_negative_allowed_by_default(self):
        assert parse_decimal_field("-1", field="delta") == Decimal("-1")

    def test_float_field_converts_and_propagates_default(self):
        assert parse_float_field("2.5", field="rate") == 2.5
        assert parse_float_field(None) is None
        assert parse_float_field("   ", default=1.5) == 1.5
        with pytest.raises(ValueError, match="cannot be negative"):
            parse_float_field("-3", allow_negative=False, field="rate")

    def test_int_field_default_invalid_and_minimum(self):
        assert parse_int_field(None, default=7) == 7
        assert parse_int_field("  ", default=8) == 8
        assert parse_int_field("12", minimum=1) == 12
        with pytest.raises(ValueError, match="must be a whole number"):
            parse_int_field("12.5", field="qty")
        with pytest.raises(ValueError, match="must be at least 1"):
            parse_int_field("0", minimum=1, field="qty")


class TestSeedManifestHelpers:
    """utils/seed_manifest.py - verdict errors and the scope aggregators."""

    def test_satisfied_by_without_expected_raises(self):
        seed_set = manifest.SeedSet(
            key="no-expectation", label="x", scope="platform", seeder=None, expected=None, source="x"
        )
        with pytest.raises(ValueError, match="declares no expected value"):
            seed_set.satisfied_by(1)

    def test_satisfied_by_with_unknown_check_raises(self):
        seed_set = manifest.SeedSet(
            key="bad-check", label="x", scope="platform", seeder=None, expected=1, source="x", check="at_most_x"
        )
        with pytest.raises(ValueError, match="unknown check"):
            seed_set.satisfied_by(1)

    def test_verdict_without_expected_is_unmeasured(self):
        seed_set = manifest.SeedSet(
            key="no-expectation", label="x", scope="platform", seeder=None, expected=None, source="x"
        )
        bucket, detail = seed_set.verdict(3)
        assert bucket == "unmeasured"
        assert "no expected declared" in detail

    def test_verdict_tenant_scope_without_tenants_is_unmeasured(self):
        seed_set = manifest.SeedSet(key="gl_chart", label="x", scope="tenant", seeder="x", expected=100, source="x")
        bucket, detail = seed_set.verdict(0, has_tenants=False)
        assert bucket == "unmeasured"
        assert "no active tenant yet" in detail

    def test_seed_sets_by_scope(self):
        platform = manifest.seed_sets_by_scope("platform")
        assert platform == manifest.PLATFORM_SEEDS
        assert all(item.scope == "platform" for item in platform)

    def test_expected_total_for_scope_fixed_and_deployment_shaped(self):
        assert manifest.expected_total_for_scope("platform") == sum(item.expected for item in manifest.PLATFORM_SEEDS)
        # Deliberate sets have expected=None by design, so the total is unknown.
        assert manifest.expected_total_for_scope("deliberate") is None


class TestTenantStorageGuards:
    """utils/tenant_limits.py - storage-walking and the storage quota check."""

    def test_storage_mb_without_app_context_is_zero(self):
        with patch("flask.has_app_context", return_value=False):
            assert tl._get_tenant_storage_mb(1) == 0

    def test_storage_mb_without_static_folder_is_zero(self, app, monkeypatch):
        monkeypatch.setattr(app, "static_folder", None)
        with app.app_context():
            assert tl._get_tenant_storage_mb(1) == 0

    def test_storage_mb_walks_both_legacy_and_canonical_trees(self, app, monkeypatch, tmp_path):
        for rel in ("uploads/tenants/1/a.bin", "uploads/products/1/b.bin"):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x" * (1024 * 1024))
        monkeypatch.setattr(app, "static_folder", str(tmp_path))
        with app.app_context():
            assert tl._get_tenant_storage_mb(1) >= 1

    def test_storage_mb_suppresses_unreadable_files(self, app, monkeypatch, tmp_path):
        target = tmp_path / "uploads" / "tenants" / "1" / "gone.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"data")
        monkeypatch.setattr(app, "static_folder", str(tmp_path))
        with app.app_context(), patch("os.path.getsize", side_effect=OSError("gone")):
            assert tl._get_tenant_storage_mb(1) == 0

    def test_storage_mb_returns_zero_when_walk_fails(self, app, monkeypatch):
        monkeypatch.setattr(app, "static_folder", str(tmp_path_placeholder()))
        with app.app_context(), patch("os.path.isdir", side_effect=RuntimeError("boom")):
            assert tl._get_tenant_storage_mb(1) == 0

    def test_check_storage_limit_no_tenant_returns(self):
        with patch.object(tl, "_active_tenant", return_value=None):
            assert tl.check_storage_limit() is None

    def test_check_storage_limit_unconfigured_returns(self):
        tenant = MagicMock(id=1, max_storage_mb=None)
        with patch.object(tl, "_active_tenant", return_value=tenant):
            assert tl.check_storage_limit() is None
        tenant.max_storage_mb = 0
        with patch.object(tl, "_active_tenant", return_value=tenant):
            assert tl.check_storage_limit() is None

    def test_check_storage_limit_below_quota_is_allowed(self):
        tenant = MagicMock(id=1, max_storage_mb=10)
        with (
            patch.object(tl, "_active_tenant", return_value=tenant),
            patch.object(tl, "_get_tenant_storage_mb", return_value=5),
        ):
            assert tl.check_storage_limit() is None

    def test_check_storage_limit_exceeded_raises(self, app):
        tl.TenantLimitError.wa_upgrade_link = ""
        tenant = MagicMock(id=1, max_storage_mb=1)
        with (
            patch.object(tl, "_active_tenant", return_value=tenant),
            patch.object(tl, "_get_tenant_storage_mb", return_value=2),
        ):
            with pytest.raises(tl.TenantLimitError) as exc:
                tl.check_storage_limit()
        assert exc.value.resource == "storage"
        assert exc.value.current == 2


def tmp_path_placeholder() -> str:
    """A harmless existing directory that is not a static tree."""
    import tempfile

    return tempfile.gettempdir()


class TestPosHelpersRemainingBranches:
    """utils/pos_helpers.py - inactive lookup, locking and session creation."""

    def test_lookup_with_include_inactive_skips_active_filter(self):
        from utils.pos_helpers import lookup_pos_product_exact

        query = MagicMock()
        query.filter.return_value.first.return_value = None
        with (
            patch("utils.pos_helpers.StockService.get_visible_products_query", return_value=query) as visible,
            patch("utils.pos_helpers.db"),
        ):
            assert lookup_pos_product_exact("NOT-A-BARCODE", include_inactive=True) == (None, {})
        visible.assert_called_once()

    def test_serialize_product_without_sku(self):
        from utils.pos_helpers import serialize_pos_product

        product = SimpleNamespace(
            id=9,
            name="مادة",
            name_ar=None,
            sku="",
            barcode=None,
            current_stock=Decimal("3"),
            unit="pcs",
            is_active=True,
            regular_price=Decimal("7"),
        )
        result = serialize_pos_product(product, {})
        assert result["text"] == "مادة"
        assert result["is_out_of_stock"] is False

    def test_safe_pos_lock_reraises_non_lock_operational_error(self):
        from sqlalchemy.exc import OperationalError

        from utils.pos_helpers import _safe_pos_lock

        savepoint = MagicMock()
        query = MagicMock()
        query.with_for_update.return_value.first.side_effect = OperationalError("statement failed", {}, Exception())
        with patch("utils.pos_helpers.db") as mock_db:
            mock_db.session.begin_nested.return_value = savepoint
            with pytest.raises(OperationalError):
                _safe_pos_lock(query, label="probe")
        savepoint.rollback.assert_called_once()

    @pytest.mark.parametrize("fn_name", ["get_active_session_locked", "get_paused_session_locked"])
    def test_locked_session_helpers_without_tenant(self, fn_name):
        import utils.pos_helpers as ph

        with patch.object(ph, "get_active_tenant_id", return_value=None):
            assert getattr(ph, fn_name)(user=None) is None

    def test_create_pos_session_with_retry_requires_tenant(self):
        import utils.pos_helpers as ph

        with patch.object(ph, "get_active_tenant_id", return_value=None):
            with pytest.raises(ValueError, match="نشطة"):
                ph.create_pos_session_with_retry(SimpleNamespace(id=42), branch_id=1)

    def test_create_pos_session_with_retry(self):
        import utils.pos_helpers as ph

        user = SimpleNamespace(id=42)

        def _generate(**kwargs):
            return kwargs["save_func"]("POS-SES-1")

        with (
            patch.object(ph, "get_active_tenant_id", return_value=7),
            patch.object(ph, "generate_number_and_save", side_effect=_generate) as generate,
            patch.object(ph, "db"),
        ):
            session = ph.create_pos_session_with_retry(
                user, branch_id=3, opening_balance=Decimal("10"), notes="n", terminal_id=" T "
            )
        assert session.tenant_id == 7
        assert session.branch_id == 3
        assert session.session_number == "POS-SES-1"
        assert session.terminal_id == "T"
        assert generate.call_count == 1

    def test_create_pos_shift_with_explicit_number_and_notes(self):
        import utils.pos_helpers as ph

        session = SimpleNamespace(id=11, tenant_id=7, branch_id=3)
        user = SimpleNamespace(id=42)
        shift = MagicMock()
        with (
            patch.object(ph.PosSessionService, "create_shift", return_value=shift) as create_shift,
            patch.object(ph, "db"),
        ):
            result = ph.create_pos_shift(session, user, notes="note", shift_number="SHF-EXPLICIT")
        assert result is shift
        assert shift.notes == "note"
        assert shift.shift_number == "SHF-EXPLICIT"
        assert shift.status == ph.PosShift.SHIFT_OPEN
        create_shift.assert_called_once()


class TestModelSmallGaps:
    """The remaining branch/serialization lines in small models."""

    def test_sale_recalculate_guards_bad_exchange_rate_and_fx_failure(self):
        from models import Payment, Sale

        sale = Sale(
            tenant_id=1,
            currency="USD",
            base_currency="AED",
            exchange_rate=Decimal("-1"),
            amount_aed=Decimal("100"),
            payment_status="unpaid",
        )
        payment = Payment(payment_confirmed=True, amount_aed=Decimal("100"), payment_method="cash")
        sale.payments = [payment]
        with patch("services.fx_revaluation_service.revalue_sale_at_settlement", side_effect=RuntimeError("fx")):
            sale.recalculate_payment_status()
        assert sale.payment_status == "paid"
        assert sale.paid_amount == Decimal("100")

    def test_payment_confirm_purchase_settlement(self):
        from models import Payment

        payment = Payment(payment_confirmed=False, amount_aed=Decimal("100"))
        payment.sale = None
        purchase = MagicMock(id=5, tenant_id=7, amount_aed=Decimal("100"))
        purchase.get_paid_amount.return_value = Decimal("100")
        payment.purchase = purchase
        with patch("services.fx_revaluation_service.revalue_purchase_at_settlement") as revalue:
            payment.confirm_payment()
        revalue.assert_called_once_with(5, 7)
        assert payment.payment_confirmed is True

    def test_payment_confirm_purchase_not_fully_paid_skips_fx(self):
        from models import Payment

        payment = Payment(payment_confirmed=False, amount_aed=Decimal("100"))
        payment.sale = None
        purchase = MagicMock(id=6, tenant_id=7, amount_aed=Decimal("100"))
        purchase.get_paid_amount.return_value = Decimal("40")
        payment.purchase = purchase
        with patch("services.fx_revaluation_service.revalue_purchase_at_settlement") as revalue:
            payment.confirm_payment()
        revalue.assert_not_called()
        assert payment.payment_confirmed is True

    def test_purchase_return_calculates_tax_without_persisted_rate(self):
        from models import PurchaseReturn, PurchaseReturnLine

        purchase_return = PurchaseReturn(tenant_id=1, currency="AED", exchange_rate=Decimal("1"))
        purchase_return.lines = [PurchaseReturnLine(line_total=Decimal("100"))]
        with (
            patch("utils.currency_utils.resolve_tenant_base_currency", return_value="AED"),
            patch("models.purchase_return.convert_and_quantize_aed", return_value=Decimal("100")),
        ):
            purchase_return.calculate_totals()
        assert purchase_return.tax_amount == Decimal("0.000")
        assert purchase_return.total_amount == Decimal("100.000")

    def test_store_product_price_defaults_and_serializers(self, db_session, sample_tenant, sample_product):
        from models import StoreProductPrice

        price = StoreProductPrice(
            tenant_id=sample_tenant.id,
            product_id=sample_product.id,
            currency_code="AED",
            price=Decimal("12.500"),
        )
        db_session.add(price)
        db_session.flush()
        assert price.created_at is not None
        assert "AED" in repr(price)
        assert price.to_dict()["price"] == "12.500"

    def test_store_provisional_order_defaults_and_serializers(self, db_session, sample_tenant):
        from models import StoreProvisionalOrder

        order = StoreProvisionalOrder(
            tenant_id=sample_tenant.id,
            provisional_number="PROV-COV-1",
            cart_json=[{"product_id": 1, "quantity": 1}],
            subtotal_tx_ccy=Decimal("10"),
            subtotal_aed=Decimal("10"),
        )
        db_session.add(order)
        db_session.flush()
        assert order.created_at is not None
        assert "PROV-COV-1" in repr(order)
        assert order.to_dict()["provisional_number"] == "PROV-COV-1"

    def test_ai_training_batch_and_knowledge_graph_to_dict(self):
        from models import AiKnowledgeGraph, AiTrainingBatch

        batch = AiTrainingBatch(source_file="f.json", file_type="json")
        graph = AiKnowledgeGraph(source_concept="a", target_concept="b", relationship_type="related_to")
        assert batch.to_dict()["source_file"] == "f.json"
        assert graph.to_dict()["relationship_type"] == "related_to"
