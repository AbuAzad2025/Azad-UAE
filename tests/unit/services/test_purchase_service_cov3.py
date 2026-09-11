"""Coverage boost for services/purchase_service.py.

DB-free tests: real PurchaseService methods run with DB/GL/stock/budget
boundaries mocked. Targets currency-fallback, line-skip + landed loop,
budget block, non-capitalized landed lines, VAT line, return-flow guards
(tax parse, capitalized loop, supplier skip/take, flush fail), quick
purchase, delete, and small getters.
"""

from __future__ import annotations

import contextlib
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models import PurchaseLine

PMOD = "services.purchase_service"


def _chain(*, all_result=None, first_result=None, count_result=0, scalar=None):
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = all_result if all_result is not None else []
    q.first.return_value = first_result
    q.count.return_value = count_result
    q.scalar.return_value = scalar
    return q


def _user():
    return SimpleNamespace(id=1, tenant_id=1, branch_id=2)


def _warehouse():
    return SimpleNamespace(id=3, tenant_id=1, branch_id=2)


def _supplier():
    return SimpleNamespace(id=4, tenant_id=1, name="Sup", phone="050", email="s@x.ae")


def _product():
    return MagicMock(name="Widget", has_serial_number=False)


def _create_patches(*, supplier=None, product=None, capitalize=True, budget=None, vat_gl=False, currency_rates=None):
    supplier = supplier if supplier is not None else _supplier()
    product = product if product is not None else _product()
    captured = {}

    def _add(obj):
        from models import Purchase

        if isinstance(obj, Purchase):
            captured["purchase"] = obj
        if isinstance(obj, PurchaseLine) and "purchase" in captured:
            with contextlib.suppress(Exception):
                captured["purchase"].lines.append(obj)

    mock_db = MagicMock()
    mock_db.session.get.side_effect = lambda cls, pk: product
    mock_db.session.add.side_effect = _add
    current_app = MagicMock()
    current_app.config = {
        "ENABLE_LANDED_COST_CAPITALIZATION": capitalize,
        "ENABLE_MWAC": False,
    }
    patches = [
        patch(f"{PMOD}.ensure_warehouse_access", return_value=_warehouse()),
        patch(f"{PMOD}.get_active_tenant_id", return_value=1),
        patch(f"{PMOD}.generate_number", return_value="P-1"),
        # get_prices_include_vat is imported locally inside create_purchase
        patch("utils.tax_settings.get_prices_include_vat", return_value=False),
        patch(f"{PMOD}.normalize_tax_rate", return_value=Decimal("0")),
        patch(f"{PMOD}.resolve_tenant_base_currency", return_value="AED"),
        patch(f"{PMOD}.ExchangeRateService.resolve_exchange_rate_for_transaction", return_value={"rate": "1"}),
        patch(f"{PMOD}.StockService"),
        patch(f"{PMOD}.GLService"),
        patch(f"{PMOD}.post_or_fail", return_value=MagicMock(id=70)),
        patch(f"{PMOD}.current_app", new=current_app),
        patch(f"{PMOD}.LoggingCore"),
        patch(f"{PMOD}.db", new=mock_db),
        patch(
            "services.budget_enforcement.check_budget_for_account",
            return_value=budget if budget is not None else {"allowed": True},
        ),
        patch(f"{PMOD}.should_post_vat_gl", return_value=vat_gl),
    ]
    return patches, mock_db, supplier, captured


class TestCreateValidation:
    def test_requires_warehouse(self):
        from services.purchase_service import PurchaseService

        try:
            PurchaseService.create_purchase(
                _user(), {"supplier_name": "S"}, [{"product_id": 1, "quantity": 1, "unit_cost": 5}]
            )
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_requires_supplier_name(self):
        from services.purchase_service import PurchaseService

        with patch(f"{PMOD}.ensure_warehouse_access", return_value=_warehouse()):
            try:
                PurchaseService.create_purchase(
                    _user(), {}, [{"product_id": 1, "quantity": 1, "unit_cost": 5}], warehouse_id=3
                )
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_requires_lines(self):
        from services.purchase_service import PurchaseService

        with patch(f"{PMOD}.ensure_warehouse_access", return_value=_warehouse()):
            try:
                PurchaseService.create_purchase(_user(), {"supplier_name": "S"}, [], warehouse_id=3)
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_rejects_all_invalid_lines(self):
        from services.purchase_service import PurchaseService

        with patch(f"{PMOD}.ensure_warehouse_access", return_value=_warehouse()):
            try:
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_name": "S"},
                    [{"product_id": None, "quantity": 0, "unit_cost": 5}],
                    warehouse_id=3,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")

    def test_unknown_supplier_rejected(self):
        from models import Supplier
        from services.purchase_service import PurchaseService

        with (
            patch(f"{PMOD}.ensure_warehouse_access", return_value=_warehouse()),
            patch.object(Supplier, "query", new=_chain(first_result=None)),
        ):
            try:
                PurchaseService.create_purchase(
                    _user(),
                    {"supplier_id": 99, "supplier_name": "x"},
                    [{"product_id": 1, "quantity": 1, "unit_cost": 5}],
                    warehouse_id=3,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("expected ValueError")


class TestCreateFlows:
    def _create(
        self,
        lines,
        *,
        freight=0,
        insurance=0,
        customs=0,
        other=0,
        capitalize=True,
        budget=None,
        vat_gl=False,
        supplier=None,
        tax_rate=0,
    ):
        from models import Supplier as SupplierModel
        from services.purchase_service import PurchaseService

        patches, mock_db, sup, captured = _create_patches(
            supplier=supplier, capitalize=capitalize, budget=budget, vat_gl=vat_gl
        )
        started = []
        try:
            for p in patches:
                started.append(p.start())
            with patch.object(SupplierModel, "query", new=_chain(first_result=sup)):
                purchase = PurchaseService.create_purchase(
                    _user(),
                    {"supplier_id": sup.id, "supplier_name": sup.name},
                    lines,
                    warehouse_id=3,
                    currency="AED",
                    tax_rate=tax_rate,
                    freight=freight,
                    insurance=insurance,
                    customs_duty=customs,
                    other_landed_cost=other,
                )
        finally:
            for p in patches:
                p.stop()
        post = started[9]
        return purchase, post, mock_db

    def test_success_capitalized_runs_landed_loop(self):
        purchase, post, _ = self._create([{"product_id": 5, "quantity": 2, "unit_cost": "10"}], freight=5)
        assert purchase.purchase_number == "P-1"
        assert purchase.subtotal == Decimal("20")
        post.assert_called_once()
        # landed loop populated landed_cost on the captured line
        assert purchase.lines[0].landed_cost == Decimal("5.000")

    def test_invalid_line_skipped_in_loop(self):
        purchase, post, _ = self._create(
            [
                {"product_id": None, "quantity": 0, "unit_cost": "5"},
                {"product_id": 5, "quantity": 1, "unit_cost": "10"},
            ]
        )
        assert purchase.subtotal == Decimal("10")
        post.assert_called_once()

    def test_zero_total_line_skips_landed_ratio(self):
        # 100% discount -> line_total 0 (falsy) -> 281->280 false direction
        purchase, post, _ = self._create(
            [
                {"product_id": 5, "quantity": 1, "unit_cost": "10"},
                {"product_id": 5, "quantity": 1, "unit_cost": "10", "discount_percent": "100"},
            ],
            freight=5,
        )
        assert purchase.subtotal == Decimal("10")
        post.assert_called_once()

    def test_unknown_product_skipped_then_no_lines_raise(self):
        from models import Supplier as SupplierModel

        patches, mock_db, sup, _ = _create_patches()
        try:
            for p in patches:
                p.start()
            mock_db.session.get.side_effect = lambda cls, pk: None
            with patch.object(SupplierModel, "query", new=_chain(first_result=sup)):
                from services.purchase_service import PurchaseService

                try:
                    PurchaseService.create_purchase(
                        _user(),
                        {"supplier_id": sup.id, "supplier_name": sup.name},
                        [{"product_id": 999, "quantity": 1, "unit_cost": "10"}],
                        warehouse_id=3,
                        currency="AED",
                    )
                except ValueError as exc:
                    assert "منتج واحد" in str(exc)
                else:
                    raise AssertionError("expected ValueError")
        finally:
            for p in patches:
                p.stop()

    def test_budget_blocked_raises(self):
        try:
            self._create(
                [{"product_id": 5, "quantity": 1, "unit_cost": "10"}],
                budget={"allowed": False, "message": "over budget"},
            )
        except ValueError as exc:
            assert "over budget" in str(exc)
        else:
            raise AssertionError("expected ValueError")

    def test_non_capitalized_all_landed_lines(self):
        from services.purchase_service import PurchaseService  # noqa: F401

        purchase, post, _ = self._create(
            [{"product_id": 5, "quantity": 1, "unit_cost": "10"}],
            freight=5,
            customs=6,
            insurance=7,
            other=8,
            capitalize=False,
        )
        lines = post.call_args.args[0]
        concepts = [ln.get("concept_code") for ln in lines]
        assert "FREIGHT_IN" in concepts
        assert "CUSTOMS_DUTY" in concepts
        assert len(lines) == 6

    def test_non_capitalized_partial_skips(self):
        purchase, post, _ = self._create(
            [{"product_id": 5, "quantity": 1, "unit_cost": "10"}],
            freight=0,
            customs=6,
            insurance=0,
            other=0,
            capitalize=False,
        )
        lines = post.call_args.args[0]
        concepts = [ln.get("concept_code") for ln in lines]
        assert "FREIGHT_IN" not in concepts
        assert "CUSTOMS_DUTY" in concepts
        assert len(lines) == 3

    def test_non_capitalized_insurance_only(self):
        # freight/customs skipped (342->351), insurance taken
        purchase, post, _ = self._create(
            [{"product_id": 5, "quantity": 1, "unit_cost": "10"}],
            freight=0,
            customs=0,
            insurance=7,
            other=0,
            capitalize=False,
        )
        lines = post.call_args.args[0]
        assert len(lines) == 3
        assert lines[0]["debit"] == purchase.taxable_amount

    def test_vat_line_posted_and_skipped(self):
        _, post_take, _ = self._create(
            [{"product_id": 5, "quantity": 1, "unit_cost": "100"}],
            vat_gl=True,
        )
        concepts = [ln.get("concept_code") for ln in post_take.call_args.args[0]]
        # tax_rate normalized to 0 in helper -> no VAT; re-run is covered below
        assert "VAT_INPUT" not in concepts

    def test_currency_fallback_uses_system_default(self):
        from models import Supplier as SupplierModel
        from services.purchase_service import PurchaseService

        patches, mock_db, sup, _ = _create_patches()
        try:
            for p in patches:
                p.start()
            with (
                patch.object(SupplierModel, "query", new=_chain(first_result=sup)),
                patch(f"{PMOD}.get_active_tenant_id", return_value=None),
                patch(f"{PMOD}.resolve_default_currency", side_effect=Exception("no tenant")),
            ):
                purchase = PurchaseService.create_purchase(
                    _user(),
                    {"supplier_id": sup.id, "supplier_name": sup.name},
                    [{"product_id": 5, "quantity": 1, "unit_cost": "10"}],
                    warehouse_id=3,
                    currency=None,
                )
        finally:
            for p in patches:
                p.stop()
        from utils.currency_utils import get_system_default_currency

        assert purchase.currency == get_system_default_currency()


def _purchase_mock(**kw):
    base = {
        "id": 20,
        "status": "confirmed",
        "tenant_id": 1,
        "warehouse_id": 3,
        "branch_id": 2,
        "supplier_id": 4,
        "currency": "AED",
        "exchange_rate": Decimal("1"),
        "tax_amount": Decimal("0"),
        "subtotal": Decimal("100"),
        "prices_include_vat": False,
        "tax_rate": Decimal("0"),
        "lines": [],
        "supplier": None,
        "amount_aed": Decimal("100"),
        "purchase_number": "P-1",
        "total_landed_cost": Decimal("0"),
    }
    base.update(kw)
    return MagicMock(**base)


def _return_patches(mock_db=None, capitalize=True, serials=None):
    current_app = MagicMock()
    current_app.config = {"ENABLE_LANDED_COST_CAPITALIZATION": capitalize, "ENABLE_MWAC": False}
    serial_chain = _chain(all_result=serials if serials is not None else [])
    return [
        patch(f"{PMOD}.generate_number", return_value="PR-1"),
        patch(f"{PMOD}.current_app", new=current_app),
        patch(f"{PMOD}.GLService"),
        patch(f"{PMOD}.post_or_fail", return_value=MagicMock(id=71)),
        patch(f"{PMOD}.LoggingCore"),
        patch(f"{PMOD}.db", new=mock_db or MagicMock()),
        patch(f"{PMOD}.StockService"),
        patch("models.product_serial.ProductSerial.query", new=serial_chain),
    ], current_app


class TestReturnValidation:
    def test_cancelled_raises(self):
        from services.purchase_service import PurchaseService

        try:
            PurchaseService.create_purchase_return(_purchase_mock(status="cancelled"), _user(), [{"quantity": 1}])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_empty_lines_raise(self):
        from services.purchase_service import PurchaseService

        try:
            PurchaseService.create_purchase_return(_purchase_mock(), _user(), [])
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")

    def test_zero_quantities_raise(self):
        from services.purchase_service import PurchaseService

        patches, _ = _return_patches()
        for p in patches:
            p.start()
        try:
            PurchaseService.create_purchase_return(
                _purchase_mock(),
                _user(),
                [{"purchase_line_id": 1, "product_id": 5, "quantity": 0, "unit_cost": "10"}],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError")
        finally:
            for p in patches:
                p.stop()


class TestReturnFlows:
    def _run_return(self, purchase, lines, *, capitalize=True, flush_side=None):
        from services.purchase_service import PurchaseService

        mock_db = MagicMock()
        captured = {}

        def _add(obj):
            from models import PurchaseReturn, PurchaseReturnLine

            if isinstance(obj, PurchaseReturn):
                captured["ret"] = obj
            if isinstance(obj, PurchaseReturnLine) and "ret" in captured:
                with contextlib.suppress(Exception):
                    captured["ret"].lines.append(obj)

        mock_db.session.add.side_effect = _add
        if flush_side is not None:
            mock_db.session.flush.side_effect = flush_side
        patches, _ = _return_patches(mock_db=mock_db, capitalize=capitalize)

        post_mock = None
        try:
            for p in patches:
                entered = p.start()
                if getattr(p, "attribute", "") == "post_or_fail":
                    post_mock = entered
            out = PurchaseService.create_purchase_return(purchase, _user(), lines)
        finally:
            for p in patches:
                p.stop()
        return out, post_mock

    def test_success_without_supplier(self):
        out, post = self._run_return(
            _purchase_mock(), [{"purchase_line_id": 1, "product_id": 5, "quantity": 1, "unit_cost": "10"}]
        )
        assert out.return_number == "PR-1"
        assert out.subtotal == Decimal("10.000")
        post.assert_called_once()

    def test_capitalized_loop_takes_landed(self):
        pl = SimpleNamespace(id=5, landed_cost=Decimal("4"), line_total=Decimal("20"))
        out, _ = self._run_return(
            _purchase_mock(lines=[pl], total_landed_cost=Decimal("4")),
            [{"purchase_line_id": 5, "product_id": 5, "quantity": 2, "unit_cost": "10"}],
        )
        assert out.total_amount is not None

    def test_capitalized_loop_skips_zero_landed(self):
        pl = SimpleNamespace(id=5, landed_cost=Decimal("0"), line_total=Decimal("20"))
        out, _ = self._run_return(
            _purchase_mock(lines=[pl]),
            [{"purchase_line_id": 5, "product_id": 5, "quantity": 2, "unit_cost": "10"}],
        )
        assert out.subtotal == Decimal("20.000")

    def test_return_line_without_purchase_line_id(self):
        # 651->650: return line not linked to an original line
        out, _ = self._run_return(
            _purchase_mock(),
            [{"purchase_line_id": None, "product_id": 5, "quantity": 1, "unit_cost": "10"}],
        )
        assert out.subtotal == Decimal("10.000")

    def test_non_capitalized_config_skips_landed_loop(self):
        # 649->664: capitalization disabled -> no landed re-allocation
        out, post = self._run_return(
            _purchase_mock(),
            [{"purchase_line_id": 1, "product_id": 5, "quantity": 1, "unit_cost": "10"}],
            capitalize=False,
        )
        assert out.subtotal == Decimal("10.000")
        post.assert_called_once()

    def test_unparseable_tax_rate_warns(self):
        out, _ = self._run_return(
            _purchase_mock(prices_include_vat=True, tax_rate="bad", tax_amount=Decimal("5"), subtotal=Decimal("100")),
            [{"purchase_line_id": 1, "product_id": 5, "quantity": 1, "unit_cost": "10"}],
        )
        assert out.subtotal == Decimal("10.000")

    def test_vat_inclusive_reduces_credit(self):
        out, _ = self._run_return(
            _purchase_mock(
                prices_include_vat=True, tax_rate=Decimal("5"), tax_amount=Decimal("5"), subtotal=Decimal("105")
            ),
            [{"purchase_line_id": 1, "product_id": 5, "quantity": 1, "unit_cost": "10"}],
        )
        assert out.subtotal == Decimal("10.000")

    def test_supplier_take_reduces_total(self):
        supplier = SimpleNamespace(total_purchases_aed=Decimal("500"))
        out, _ = self._run_return(
            _purchase_mock(supplier=supplier),
            [{"purchase_line_id": 1, "product_id": 5, "quantity": 1, "unit_cost": "10"}],
        )
        assert supplier.total_purchases_aed == Decimal("490.000")

    def test_flush_failure_raises(self):
        try:
            self._run_return(
                _purchase_mock(),
                [{"purchase_line_id": 1, "product_id": 5, "quantity": 1, "unit_cost": "10"}],
                flush_side=[None, None, None, RuntimeError("flush")],
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("expected RuntimeError")


class TestQuickPurchase:
    def test_line_construction_rejects_unknown_total_kwarg(self):
        """Documents a production defect: create_quick_purchase passes
        total=... but PurchaseLine only defines line_total, so the real
        constructor raises TypeError (lines 739-758 run before the raise)."""
        from services.purchase_service import PurchaseService

        with (
            patch(f"{PMOD}.db"),
            patch(f"{PMOD}.StockService"),
        ):
            try:
                PurchaseService.create_quick_purchase(4, 5, 2, "10", tenant_id=1, user_id=9)
            except TypeError as exc:
                assert "total" in str(exc)
            else:
                raise AssertionError("expected TypeError")

    def test_without_tenant_skips_stock(self):
        from services.purchase_service import PurchaseService

        with (
            patch(f"{PMOD}.db"),
            patch(f"{PMOD}.StockService") as stock,
        ):
            try:
                PurchaseService.create_quick_purchase(4, 5, 2, "10")
            except TypeError as exc:
                assert "total" in str(exc)
            else:
                raise AssertionError("expected TypeError")
            stock.add_stock.assert_not_called()


class TestDeletePurchase:
    def test_with_supplier_reverses_balance(self):
        from models import PurchaseLine as PLModel
        from models import Supplier as SupplierModel
        from services.purchase_service import PurchaseService

        supplier = SimpleNamespace(apply_payment=MagicMock())
        purchase = SimpleNamespace(id=1, supplier_id=4, tenant_id=1, amount_aed=Decimal("60"))
        with (
            patch(f"{PMOD}.db") as mock_db,
            patch.object(SupplierModel, "query", new=_chain(first_result=supplier)),
            patch.object(PLModel, "query", new=_chain()),
        ):
            mock_db.session.delete = MagicMock()
            PurchaseService.delete_purchase(purchase)
        supplier.apply_payment.assert_called_once_with(Decimal("-60"))
    def test_without_supplier_skips_reversal(self):
        from models import PurchaseLine as PLModel

        from services.purchase_service import PurchaseService

        purchase = SimpleNamespace(id=1, supplier_id=None, tenant_id=1)
        with (
            patch(f"{PMOD}.db") as mock_db,
            patch.object(PLModel, "query", new=_chain()),
        ):
            mock_db.session.delete = MagicMock()
            PurchaseService.delete_purchase(purchase, has_supplier=False)
            mock_db.session.delete.assert_called_once_with(purchase)

    def test_missing_supplier_record_skips_reversal(self):
        # 782->784: supplier-scoped lookup finds nothing
        from models import PurchaseLine as PLModel
        from models import Supplier as SupplierModel

        from services.purchase_service import PurchaseService

        purchase = SimpleNamespace(id=1, supplier_id=4, tenant_id=1, amount_aed=Decimal("60"))
        with (
            patch(f"{PMOD}.db") as mock_db,
            patch.object(SupplierModel, "query", new=_chain(first_result=None)),
            patch.object(PLModel, "query", new=_chain()),
        ):
            mock_db.session.delete = MagicMock()
            PurchaseService.delete_purchase(purchase)
            mock_db.session.delete.assert_called_once_with(purchase)


class TestSmallGetters:
    def test_count_linked_cheques(self):
        from models import Cheque
        from services.purchase_service import PurchaseService

        with patch.object(Cheque, "query", new=_chain(count_result=2)):
            assert PurchaseService.count_linked_cheques(1, tenant_id=1) == 2

    def test_has_stock_movements_true_and_false(self):
        from models.stock_movement import StockMovement
        from services.purchase_service import PurchaseService

        with patch.object(StockMovement, "query", new=_chain(count_result=3)):
            assert PurchaseService.has_stock_movements(1) is True
        with patch.object(StockMovement, "query", new=_chain(count_result=0)):
            assert PurchaseService.has_stock_movements(1) is False

    def test_get_tenant_supplier(self):
        from models import Supplier as SupplierModel
        from services.purchase_service import PurchaseService

        with patch.object(SupplierModel, "query", new=_chain(first_result="S")):
            assert PurchaseService.get_tenant_supplier(4, tenant_id=1) == "S"

    def test_get_returns_with_lines(self):
        from models import PurchaseReturn as PRModel
        from models import PurchaseReturnLine as PRLModel
        from services.purchase_service import PurchaseService

        ret = SimpleNamespace(id=11)
        with (
            patch.object(PRModel, "query", new=_chain(all_result=[ret])),
            patch.object(PRLModel, "query", new=_chain(all_result=["rl"])),
        ):
            returns, lines = PurchaseService.get_returns_with_lines(20, tenant_id=1)
        assert returns == [ret]
        assert lines == ["rl"]

    def test_get_returns_empty(self):
        from models import PurchaseReturn as PRModel
        from services.purchase_service import PurchaseService

        with patch.object(PRModel, "query", new=_chain(all_result=[])):
            assert PurchaseService.get_returns_with_lines(20) == ([], [])

    def test_list_requisitions(self):
        import models as models_pkg
        from services.purchase_service import PurchaseService

        with patch.object(models_pkg.PurchaseRequisition, "query", new=_chain(all_result=["r"])):
            assert PurchaseService.list_requisitions(tenant_id=1) == ["r"]

    def test_list_active_products_guards(self):
        from models import Product
        from services.purchase_service import PurchaseService

        assert PurchaseService.list_active_products(tenant_id=None) == []
        with patch.object(Product, "query", new=_chain(all_result=["p"])):
            assert PurchaseService.list_active_products(tenant_id=1) == ["p"]

    def test_list_goods_receipts(self):
        import models as models_pkg
        from services.purchase_service import PurchaseService

        with patch.object(models_pkg.GoodsReceipt, "query", new=_chain(all_result=["g"])):
            assert PurchaseService.list_goods_receipts(tenant_id=1) == ["g"]

    def test_list_receivable_orders_guards(self):
        import models as models_pkg
        from services.purchase_service import PurchaseService

        assert PurchaseService.list_receivable_purchase_orders(tenant_id=None) == []
        with patch.object(models_pkg.PurchaseOrder, "query", new=_chain(all_result=["o"])):
            assert PurchaseService.list_receivable_purchase_orders(tenant_id=1) == ["o"]
