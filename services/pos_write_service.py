"""POS write service - handles POS-specific DB operations."""

from __future__ import annotations

import logging

from extensions import db

logger = logging.getLogger(__name__)


class PosWriteService:
    """Pure business logic for POS write operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_order_type(
        tenant_id: int,
        code: str,
        name_ar: str = "",
        name_en: str = "",
        is_active: bool = True,
        sort_order: int = 0,
        is_default: bool = False,
        kds_enabled: bool = False,
    ):
        """Create a new POS order type."""
        from models import PosOrderType

        if PosOrderType.get_by_code(tenant_id, code):
            raise ValueError("رمز النوع موجود مسبقاً")

        order_type = PosOrderType(
            tenant_id=tenant_id,
            code=code,
            name_ar=name_ar.strip() or code,
            name_en=name_en.strip() or None,
            is_active=is_active,
            sort_order=sort_order,
            is_default=is_default,
            kds_enabled=kds_enabled,
        )
        db.session.add(order_type)
        return order_type

    @staticmethod
    def delete_order_type(order_type):
        """Delete a POS order type."""
        db.session.delete(order_type)

    @staticmethod
    def create_floor(
        tenant_id: int,
        name: str,
        name_ar: str = "",
        sort_order: int = 0,
    ):
        """Create a new restaurant floor."""
        from models import PosFloor

        floor = PosFloor(
            tenant_id=tenant_id,
            name=name,
            name_ar=name_ar or None,
            sort_order=sort_order,
            is_active=True,
        )
        db.session.add(floor)
        return floor

    @staticmethod
    def create_table(tenant_id: int, floor_id: int, name: str, seats: int = 4, pos_x: int = 0, pos_y: int = 0):
        """Create a new restaurant table."""
        from models import PosTable

        table = PosTable(
            tenant_id=tenant_id,
            floor_id=floor_id,
            label=name,
            capacity=seats,
            pos_x=pos_x,
            pos_y=pos_y,
            is_active=True,
        )
        db.session.add(table)
        return table

    @staticmethod
    def create_table_order_model(tenant_id: int, table_id: int, sale_id: int, guest_count: int = 1):
        """Create a new table order (restaurant dine-in)."""
        from models import PosTableOrder

        torder = PosTableOrder(
            tenant_id=tenant_id,
            table_id=table_id,
            sale_id=sale_id,
            guest_count=guest_count,
        )
        db.session.add(torder)
        return torder

    @staticmethod
    def create_kds_order(
        tenant_id: int,
        sale_id: int,
        session_id: int | None = None,
        branch_id: int | None = None,
        order_number: str = "",
        items_json: str = "[]",
        notes: str = "",
    ):
        """Create a new KDS (Kitchen Display System) order."""
        from models import PosKdsOrder

        kds_order = PosKdsOrder(
            tenant_id=tenant_id,
            sale_id=sale_id,
            session_id=session_id,
            branch_id=branch_id,
            order_number=order_number,
            items_json=items_json,
            status="pending",
            notes=notes,
        )
        db.session.add(kds_order)
        return kds_order

    @staticmethod
    def create_printer(
        tenant_id: int,
        name: str,
        role: str = "customer",
        connection_type: str = "agent_network",
        host: str | None = None,
        port: int | None = None,
        serial_port: str | None = None,
        baud_rate: int | None = None,
        encoding: str = "cp864",
        category_ids: list | None = None,
        is_active: bool = True,
        sort_order: int = 0,
    ):
        """Create a new POS printer."""
        from models import PosPrinter

        printer = PosPrinter(
            tenant_id=tenant_id,
            name=name,
            role=role,
            connection_type=connection_type,
            host=host,
            port=port,
            serial_port=serial_port,
            baud_rate=baud_rate,
            encoding=encoding,
            category_ids=category_ids or [],
            is_active=is_active,
            sort_order=sort_order,
        )
        db.session.add(printer)
        return printer

    @staticmethod
    def delete_printer(printer):
        """Delete a POS printer."""
        db.session.delete(printer)

    # ─── Route-facing scoped fetches ───

    @staticmethod
    def latest_system_settings():
        """Most recent global SystemSettings row (or None)."""
        from models.system_settings import SystemSettings

        return SystemSettings.query.order_by(SystemSettings.id.desc()).first()

    @staticmethod
    def products_by_ids(product_ids, tenant_id):
        """Tenant-scoped products keyed by id for the given ids (empty dict when absent)."""
        from models import Product

        rows = db.session.query(Product).filter(Product.id.in_(product_ids), Product.tenant_id == tenant_id).all()
        return {p.id: p for p in rows}

    @staticmethod
    def session_sales(tenant_id, session_id):
        """All sales recorded against a POS session (tenant-scoped)."""
        from models import Sale

        return Sale.query.filter(Sale.tenant_id == tenant_id, Sale.pos_session_id == session_id).all()

    @staticmethod
    def recent_session_sales(tenant_id, session_id, limit=5):
        """Newest sales of a POS session (tenant-scoped, id-descending)."""
        from models import Sale

        return (
            Sale.query.filter(Sale.tenant_id == tenant_id, Sale.pos_session_id == session_id)
            .order_by(Sale.id.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def shift_cash_movements(tenant_id, shift_id):
        """Pay-in/out cash movements recorded for a shift (tenant-scoped)."""
        from models.pos_cash_movement import PosCashMovement

        return PosCashMovement.query.filter(
            PosCashMovement.tenant_id == tenant_id,
            PosCashMovement.shift_id == shift_id,
        ).all()

    @staticmethod
    def kds_order_for_sale(sale_id, tenant_id):
        """KDS order linked to a sale (tenant-scoped) or None."""
        from models import PosKdsOrder

        return PosKdsOrder.query.filter_by(sale_id=sale_id, tenant_id=tenant_id).first()
