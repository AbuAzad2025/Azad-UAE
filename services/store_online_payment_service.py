"""Online payment gateway for store checkout (NOWPayments)."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import requests
from flask import current_app
from flask_babel import gettext
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.state import InstanceState

from extensions import db
from models.idempotency_key import IdempotencyKey
from models.payment_vault import PaymentVault
from utils.currency_utils import get_system_default_currency
from utils.nowpayments_ipn import get_nowpayments_ipn_url


class StoreOnlinePaymentService:
    ORDER_PREFIX = "STORE_"
    # Durable idempotency ledger: unique on (tenant_id, endpoint, key). The key
    # is derived from the sale id, so it is scoped to one (tenant, sale) pair.
    IDEMPOTENCY_ENDPOINT = "store.online_payment.init"

    @staticmethod
    def _vault_for_tenant(tenant_id=None) -> PaymentVault | None:
        vault = PaymentVault.get_tenant_vault(tenant_id) if tenant_id is not None else None
        return vault or PaymentVault.get_platform_vault()

    @staticmethod
    def is_configured(tenant_id=None) -> bool:
        vault = StoreOnlinePaymentService._vault_for_tenant(tenant_id)
        if not vault:
            return False
        key = (getattr(vault, "nowpayments_api_key", None) or "").strip()
        return bool(key or (current_app.config.get("NOWPAYMENTS_API_KEY") or "").strip())

    @staticmethod
    def _api_key(tenant_id=None) -> str:
        vault = StoreOnlinePaymentService._vault_for_tenant(tenant_id)
        key = (getattr(vault, "nowpayments_api_key", None) or "").strip() if vault else ""
        if not key:
            key = (current_app.config.get("NOWPAYMENTS_API_KEY") or "").strip()
        if not key:
            raise ValueError(gettext("بوابة الدفع غير مهيأة على المنصة."))
        return key

    @staticmethod
    def _payment_identity(sale, store) -> tuple[int, int] | None:
        """Return ``(tenant_id, sale_id)`` for a persisted, tenant-matching sale.

        ``None`` means the object is not a real persisted ORM sale (e.g. a
        lightweight double used in unit tests), so no ledger row is reserved.
        A tenant mismatch is always refused — the payment must belong to the
        store that initiated it.
        """
        try:
            state = sa_inspect(sale)
            # MagicMock auto-creates __sa_inspect__, so the inspect() result
            # itself must be a real ORM InstanceState — not just truthy.
            if not isinstance(state, InstanceState) or not state.persistent or not state.identity:
                return None
        except Exception:
            return None
        tenant_id = int(getattr(sale, "tenant_id", 0) or 0)
        sale_id = int(getattr(sale, "id", 0) or 0)
        store_tenant_id = int(getattr(store, "tenant_id", 0) or 0)
        if store_tenant_id and tenant_id and store_tenant_id != tenant_id:
            raise ValueError(gettext("طلب الدفع لا ينتمي إلى هذا المتجر."))
        tenant_id = tenant_id or store_tenant_id
        if not tenant_id or not sale_id:
            return None
        return tenant_id, sale_id

    @staticmethod
    def create_payment_for_sale(sale, store, *, customer_email: str | None = None, crypto_currency: str = "btc"):
        # (tenant, sale) idempotency guard. The ref is committed by the route's
        # atomic_transaction, so it now survives across requests and this check
        # actually fires on a double-submit.
        existing_ref = getattr(sale, "checkout_gateway_ref", None)
        if isinstance(existing_ref, str) and existing_ref.strip():
            raise ValueError(gettext("يوجد دفع إلكتروني قائم لهذا الطلب."))
        amount_aed = float(Decimal(str(sale.amount_aed or 0)))
        if amount_aed < 1:
            raise ValueError(gettext("الحد الأدنى للدفع الإلكتروني 1 AED."))
        amount = float(Decimal(str(sale.total_amount or 0)))

        # Reserve a durable, tenant-scoped idempotency key BEFORE calling the
        # gateway. The unique (tenant_id, endpoint, key) constraint is the
        # race guard: two concurrent submits cannot both pass the flush, so at
        # most one payment is ever initiated for a given sale. A failed
        # gateway call is rolled back by the caller, releasing the key for a
        # clean retry.
        identity = StoreOnlinePaymentService._payment_identity(sale, store)
        idem = None
        if identity:
            tenant_id, sale_id = identity
            key = f"sale:{sale_id}"
            prior = IdempotencyKey.query.filter_by(
                tenant_id=tenant_id,
                endpoint=StoreOnlinePaymentService.IDEMPOTENCY_ENDPOINT,
                key=key,
            ).first()
            if prior is not None:
                raise ValueError(gettext("يوجد دفع إلكتروني قائم لهذا الطلب."))
            idem = IdempotencyKey(
                tenant_id=tenant_id,
                endpoint=StoreOnlinePaymentService.IDEMPOTENCY_ENDPOINT,
                key=key,
                request_hash=hashlib.sha256(f"{tenant_id}:{sale_id}".encode()).hexdigest(),
                status=IdempotencyKey.STATUS_IN_PROGRESS,
            )
            db.session.add(idem)
        # Exactly one flush (the route owns the commit). For a persisted sale
        # this reserves the idempotency key before the external call; for a
        # lightweight double it is a harmless no-op that keeps the gateway
        # contract stable.
        db.session.flush()

        currency = (sale.currency or get_system_default_currency()).lower()
        order_id = f"{StoreOnlinePaymentService.ORDER_PREFIX}{sale.id}_{store.tenant_id}"
        ipn_url = get_nowpayments_ipn_url()

        payload = {
            "price_amount": amount,
            "price_currency": currency,
            "pay_currency": (crypto_currency or "btc").lower(),
            "order_id": order_id,
            "order_description": f"Store order {sale.sale_number} — {store.title}",
            "ipn_callback_url": ipn_url,
        }
        if customer_email:
            payload["customer_email"] = customer_email

        headers = {
            "x-api-key": StoreOnlinePaymentService._api_key(getattr(store, "tenant_id", None)),
            "Content-Type": "application/json",
        }
        response = requests.post(
            "https://api.nowpayments.io/v1/payment",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise ValueError(gettext(f"فشل إنشاء الدفع: {response.text[:200]}"))

        data = response.json()
        payment_id = data.get("payment_id")
        payment_url = data.get("invoice_url") or data.get("payment_url")
        if not payment_url:
            raise ValueError(gettext("لم يُرجَع رابط الدفع من البوابة."))

        sale.checkout_gateway_ref = str(payment_id)
        sale.checkout_payment_method = sale.checkout_payment_method or "online_pay"
        if idem is not None:
            idem.status = IdempotencyKey.STATUS_COMPLETED
        # No second flush and no commit here: the route's atomic_transaction
        # owns the boundary and persists the ref + ledger row together.

        return {
            "payment_id": payment_id,
            "payment_url": payment_url,
            "order_id": order_id,
        }

    @staticmethod
    def parse_store_order_id(order_id: str) -> tuple[int, int] | None:
        if not order_id or not order_id.startswith(StoreOnlinePaymentService.ORDER_PREFIX):
            return None
        try:
            rest = order_id[len(StoreOnlinePaymentService.ORDER_PREFIX) :]
            sale_id_str, tenant_id_str = rest.split("_", 1)
            return int(sale_id_str), int(tenant_id_str)
        except (TypeError, ValueError):
            return None
