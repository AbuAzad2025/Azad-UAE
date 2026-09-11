"""Coverage boost for services/pos_checkout_service.py.

Targets: walkin/inactive-customer, warehouse, empty-lines, merge-error,
discount InvalidOperation + percent rows, serial mismatch, price-permission,
promotion failure, paid-amount parse, missing method, split-tender error,
multi-tender gate, qa marker, discount override token, order-type fallback,
table id paths, cash/change accumulation, kds branch, tenders in response.
Real PosCheckoutService.checkout; collaborators that own DB writes
(SaleService/PromotionService/PosWriteService) are stubbed at the boundary.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from services.pos_checkout_service import PosCheckoutError, PosCheckoutService


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _base_payload(product_id, **over):
    payload = {
        "customer_id": None,
        "walkin": True,
        "lines": [{"product_id": product_id, "quantity": 1}],
        "payment_method": "cash",
        "paid_amount": 0,
    }
    payload.update(over)
    return payload


def _session(tenant_id, branch_id, user_id):
    from models.pos_session import PosSession

    return PosSession(
        tenant_id=tenant_id,
        branch_id=branch_id,
        user_id=user_id,
        session_number=_uniq("POS-SES"),
        opening_balance_cash=Decimal("0"),
        status=PosSession.STATUS_OPEN,
    )


def _stub_sale(mocker, tenant_id=1, total="50", number=None, customer_id=1, seller_id=1):
    from extensions import db
    from models import Sale

    number = number or _uniq("S")

    def _fake_create_sale(*args, **kwargs):
        cust = kwargs.get("customer")
        sell = kwargs.get("seller")

        def _int_or(value, default):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        sale = Sale(
            tenant_id=tenant_id,
            sale_number=number,
            customer_id=_int_or(getattr(cust, "id", None), customer_id),
            seller_id=_int_or(getattr(sell, "id", None), seller_id),
            sale_date=__import__("datetime").datetime.now(__import__("datetime").UTC),
            status="confirmed",
            payment_status="paid",
            subtotal=Decimal(total),
            total_amount=Decimal(total),
            amount=Decimal(total),
            amount_aed=Decimal(total),
            currency="AED",
        )
        db.session.add(sale)
        db.session.flush()
        return sale

    mocker.patch(
        "services.pos_checkout_service.SaleService.create_sale",
        side_effect=_fake_create_sale,
    )
    mocker.patch(
        "services.pos_checkout_service.PosWriteService.create_kds_order",
        return_value=SimpleNamespace(id=5),
    )
    return None


class TestCustomerWarehouseLines:
    def test_walkin_value_error_maps_to_checkout_error(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", side_effect=ValueError("nope"))
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_inactive_customer_rejected(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, mocker
    ):
        from unittest.mock import MagicMock

        inactive = MagicMock(id=999, is_active=False)
        mocker.patch("services.pos_checkout_service.tenant_get", return_value=inactive)
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id, customer_id=999, walkin=False),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_bad_warehouse_maps_to_checkout_error(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer")
        mocker.patch("services.pos_checkout_service.ensure_warehouse_access", side_effect=ValueError("bad wh"))
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id, warehouse_id=9999),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_empty_lines_rejected(self, db_session, sample_tenant, sample_branch, sample_user, mocker):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer")
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(1, lines=[]),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_merge_error_maps_to_checkout_error(self, db_session, sample_tenant, sample_branch, sample_user, mocker):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer")
        mocker.patch("services.pos_checkout_service.merge_checkout_lines", side_effect=ValueError("bad cart"))
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(1),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_inactive_product_rejected(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer")
        sample_product.is_active = False
        db_session.flush()
        db_session.commit()
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )


class TestDiscountSerialPrice:
    def test_discount_invalid_operation_treated_as_no_discount(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, sample_customer, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=sample_customer)
        mocker.patch("services.pos_checkout_service.tenant_get", return_value=None)
        _stub_sale(mocker, tenant_id=sample_tenant.id)
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        sample_user.has_permission = lambda code: True
        resp, _ = PosCheckoutService.checkout(
            payload=_base_payload(sample_product.id, discount_amount="not-a-number"),
            user=sample_user,
            session=sess,
            shift=None,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            promotions_enabled=False,
            multi_tender_allowed=True,
        )
        assert resp["success"] is True

    def test_serial_count_mismatch_rejected(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, mocker
    ):
        from unittest.mock import MagicMock

        sample_product.has_serial_number = True
        db_session.flush()
        db_session.commit()
        walkin = MagicMock(id=78, customer_type="individual", name="W")
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=walkin)
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_price_override_without_permission_denied(
        self, db_session, sample_tenant, sample_branch, sample_product, mocker
    ):
        from unittest.mock import MagicMock

        walkin = MagicMock(id=79, customer_type="individual", name="W")
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=walkin)
        user = MagicMock(id=9, is_owner=False)
        user.has_permission = lambda code: False
        sess = _session(sample_tenant.id, sample_branch.id, 9)
        with pytest.raises(PosCheckoutError) as exc:
            PosCheckoutService.checkout(
                payload=_base_payload(
                    sample_product.id, lines=[{"product_id": sample_product.id, "quantity": 1, "unit_price": "99999"}]
                ),
                user=user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )
        assert exc.value.status_code == 403


class TestPaymentsTendersGates:
    def test_promotion_exception_is_swallowed(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, sample_customer, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=sample_customer)
        mocker.patch(
            "services.pos_checkout_service.PromotionService.evaluate_cart", side_effect=RuntimeError("promo down")
        )
        _stub_sale(mocker, tenant_id=sample_tenant.id)
        sample_user.has_permission = lambda code: True
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        resp, _ = PosCheckoutService.checkout(
            payload=_base_payload(sample_product.id),
            user=sample_user,
            session=sess,
            shift=None,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            promotions_enabled=True,
            multi_tender_allowed=True,
        )
        assert resp["promotion_discount"] == 0.0

    def test_paid_amount_unparseable_and_missing_method(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, sample_customer, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=sample_customer)
        sample_user.has_permission = lambda code: True
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        # unparseable paid_amount -> treated as 0, checkout proceeds
        _stub_sale(mocker, tenant_id=sample_tenant.id)
        resp, _ = PosCheckoutService.checkout(
            payload=_base_payload(sample_product.id, paid_amount="bad-amount"),
            user=sample_user,
            session=sess,
            shift=None,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            promotions_enabled=False,
            multi_tender_allowed=True,
        )
        assert resp["success"] is True
        # positive amount without method -> error
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id, paid_amount=10, payment_method=""),
                user=sample_user,
                session=_session(sample_tenant.id, sample_branch.id, sample_user.id),
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )

    def test_split_tender_error_and_multi_tender_gate(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, mocker
    ):
        from unittest.mock import MagicMock

        walkin = MagicMock(id=82, customer_type="individual", name="W")
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=walkin)
        sample_user.has_permission = lambda code: True
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        with pytest.raises(PosCheckoutError):
            PosCheckoutService.checkout(
                payload=_base_payload(sample_product.id, payments=[{"bad": 1}]),
                user=sample_user,
                session=sess,
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=True,
            )
        with pytest.raises(PosCheckoutError) as exc:
            PosCheckoutService.checkout(
                payload=_base_payload(
                    sample_product.id,
                    payments=[{"amount": 5, "payment_method": "cash"}, {"amount": 5, "payment_method": "card"}],
                ),
                user=sample_user,
                session=_session(sample_tenant.id, sample_branch.id, sample_user.id),
                shift=None,
                tenant_id=sample_tenant.id,
                branch_id=sample_branch.id,
                promotions_enabled=False,
                multi_tender_allowed=False,
            )
        assert exc.value.status_code == 403


class TestPostSaleBranches:
    def test_qa_marker_table_invalid_and_change_with_shift(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, sample_customer, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=sample_customer)
        _stub_sale(mocker, tenant_id=sample_tenant.id, total="10")
        sample_user.has_permission = lambda code: True
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        db_session.add(sess)
        db_session.flush()
        shift = SimpleNamespace(total_change_given=Decimal("0"))
        resp, _ = PosCheckoutService.checkout(
            payload=_base_payload(
                sample_product.id,
                qa_marker=True,
                notes="n",
                table_id="not-an-int",
                payment_method="cash",
                paid_amount=50,
            ),
            user=sample_user,
            session=sess,
            shift=shift,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            promotions_enabled=False,
            multi_tender_allowed=True,
        )
        assert resp["success"] is True
        assert Decimal(str(sess.total_change_given)) > Decimal("0")

    def test_split_tender_response_and_kds_delivery_fallback(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, sample_customer, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=sample_customer)
        from models.pos_order_type import PosOrderType

        db_session.add(
            PosOrderType(
                tenant_id=sample_tenant.id,
                code="delivery",
                name_ar="توصيل",
                name_en="Delivery",
                is_active=True,
                sort_order=30,
                is_default=True,
                kds_enabled=True,
            )
        )
        db_session.flush()
        _stub_sale(mocker, tenant_id=sample_tenant.id, total="10")
        sample_user.has_permission = lambda code: True
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        resp, kds = PosCheckoutService.checkout(
            payload=_base_payload(
                sample_product.id, order_type="delivery", payments=[{"amount": 10, "payment_method": "cash"}]
            ),
            user=sample_user,
            session=sess,
            shift=None,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            promotions_enabled=False,
            multi_tender_allowed=True,
        )
        assert resp["order_type"] == "delivery"
        assert resp["tenders"][0]["method"] == "cash"
        assert kds is not None

    def test_discount_override_token_consumed_and_audited(
        self, db_session, sample_tenant, sample_branch, sample_user, sample_product, sample_customer, mocker
    ):
        mocker.patch("services.pos_checkout_service.get_pos_walkin_customer", return_value=sample_customer)
        _stub_sale(mocker, tenant_id=sample_tenant.id)
        sample_user.has_permission = lambda code: True
        require = mocker.patch(
            "services.pos_checkout_service.PosOverrideService.require_permission_or_override", return_value=123
        )
        audit = mocker.patch("services.pos_checkout_service.LoggingCore.log_audit")
        sess = _session(sample_tenant.id, sample_branch.id, sample_user.id)
        resp, _ = PosCheckoutService.checkout(
            payload=_base_payload(sample_product.id, discount_amount=5, override_token="tok"),
            user=sample_user,
            session=sess,
            shift=None,
            tenant_id=sample_tenant.id,
            branch_id=sample_branch.id,
            promotions_enabled=False,
            multi_tender_allowed=True,
        )
        assert resp["success"] is True
        require.assert_called_once()
        assert any(c.args[0] == "pos_discount_override" for c in audit.call_args_list)
