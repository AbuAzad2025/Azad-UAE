"""Read-model queries backing routes/reports.py.

Every method relocates a former inline route query behavior-identically:
same filters, ordering, limits, scoping and terminal operations. The bulk
grouped-query blocks (partner/merchant financials, supplier summary,
receivables aging inputs, stock movement maps) are preserved exactly.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from flask_babel import gettext
from sqlalchemy import func, select

from extensions import db
from models.payment import payment_affects_balance
from utils.cache_decorators import cached_query
from utils.decorators import report_branch_scope_id
from utils.tenanting import tenant_get_or_404, tenant_query

__all__ = ["ReportsQueryService"]


class ReportsQueryService:
    # ------------------------------------------------------------------
    # Cached payment totals
    # ------------------------------------------------------------------
    @staticmethod
    @cached_query(timeout=60, key_prefix="sale_paid")
    def get_confirmed_sale_paid_aed(sale_id, tenant_id=None, branch_id=None):
        from models import Payment

        q = db.session.query(func.coalesce(func.sum(Payment.amount_aed), 0)).filter(
            Payment.sale_id == sale_id,
            payment_affects_balance(Payment),
            Payment.direction == "incoming",
        )
        if tenant_id is not None:
            q = q.filter(Payment.tenant_id == tenant_id)
        if branch_id is not None:
            q = q.filter(Payment.branch_id == branch_id)
        return Decimal(str(q.scalar() or 0))

    @staticmethod
    @cached_query(timeout=60, key_prefix="supplier_paid")
    def get_confirmed_supplier_paid_aed(supplier_id, purchase_id=None, tenant_id=None, branch_id=None):
        from models import Payment

        q = db.session.query(func.coalesce(func.sum(Payment.amount_aed), 0)).filter(
            Payment.supplier_id == supplier_id,
            payment_affects_balance(Payment),
            Payment.direction == "outgoing",
        )
        if purchase_id is not None:
            q = q.filter(Payment.purchase_id == purchase_id)
        if tenant_id is not None:
            q = q.filter(Payment.tenant_id == tenant_id)
        if branch_id is not None:
            q = q.filter(Payment.branch_id == branch_id)
        return Decimal(str(q.scalar() or 0))

    # ------------------------------------------------------------------
    # Branch-scoped entity queries
    # ------------------------------------------------------------------
    @staticmethod
    def _scoped_customer_query():
        from models import Customer
        from models import Payment
        from models.receipt import Receipt

        query = tenant_query(Customer)
        scoped_branch_id = report_branch_scope_id()
        if scoped_branch_id is None:
            return query

        sale_ids = select(Sale.customer_id).where(Sale.customer_id.isnot(None), Sale.branch_id == scoped_branch_id)
        payment_ids = select(Payment.customer_id).where(
            Payment.customer_id.isnot(None), Payment.branch_id == scoped_branch_id
        )
        receipt_ids = select(Receipt.customer_id).where(
            Receipt.customer_id.isnot(None), Receipt.branch_id == scoped_branch_id
        )
        return query.filter(Customer.id.in_(sale_ids.union(payment_ids, receipt_ids)))

    @staticmethod
    def _scoped_supplier_query():
        from models import Payment
        from models import Purchase
        from models import Supplier

        scoped_branch_id = report_branch_scope_id()
        if scoped_branch_id is None:
            return tenant_query(Supplier)

        purchase_ids = select(Purchase.supplier_id).where(
            Purchase.supplier_id.isnot(None), Purchase.branch_id == scoped_branch_id
        )
        payment_ids = select(Payment.supplier_id).where(
            Payment.supplier_id.isnot(None), Payment.branch_id == scoped_branch_id
        )
        return tenant_query(Supplier).filter(Supplier.id.in_(purchase_ids.union(payment_ids)))

    @staticmethod
    def supplier_in_branch_scope(record_id):
        from models import Supplier

        return bool(
            db.session.query(ReportsQueryService._scoped_supplier_query().filter_by(id=record_id).exists()).scalar()
        )

    @staticmethod
    def customer_in_branch_scope(record_id):
        from models import Customer

        return bool(
            db.session.query(ReportsQueryService._scoped_customer_query().filter_by(id=record_id).exists()).scalar()
        )

    # ------------------------------------------------------------------
    # Partners / merchants / suppliers report (bulk grouped queries)
    # ------------------------------------------------------------------
    @staticmethod
    def build_partners_report(date_from, date_to, tenant_id, scoped_branch_id):
        from models import Customer, PartnerCommissionEntry, Product, Purchase, Sale, SaleLine
        from models import Payment
        from models.receipt import Receipt

        partners_data = []
        partner_share_totals = {}

        entries_query = (
            db.session.query(PartnerCommissionEntry.id)
            .join(Sale, PartnerCommissionEntry.sale_id == Sale.id)
            .filter(Sale.status == "confirmed")
        )
        if tenant_id is not None:
            entries_query = entries_query.filter(PartnerCommissionEntry.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            entries_query = entries_query.filter(PartnerCommissionEntry.branch_id == scoped_branch_id)
        if date_from:
            entries_query = entries_query.filter(func.date(Sale.sale_date) >= date_from)
        if date_to:
            entries_query = entries_query.filter(func.date(Sale.sale_date) <= date_to)

        has_entries = db.session.query(entries_query.exists()).scalar()

        if has_entries:
            rows = (
                db.session.query(
                    Product.name.label("product_name"),
                    Customer.name.label("partner_name"),
                    PartnerCommissionEntry.percentage.label("percentage"),
                    func.coalesce(func.sum(SaleLine.quantity), 0).label("total_qty"),
                    func.coalesce(func.sum(PartnerCommissionEntry.base_amount_aed), 0).label("total_revenue"),
                    func.coalesce(func.sum(PartnerCommissionEntry.commission_amount_aed), 0).label("partner_share_amount"),
                    Customer.id.label("partner_id"),
                )
                .join(Sale, PartnerCommissionEntry.sale_id == Sale.id)
                .join(Customer, PartnerCommissionEntry.partner_customer_id == Customer.id)
                .outerjoin(SaleLine, PartnerCommissionEntry.sale_line_id == SaleLine.id)
                .outerjoin(Product, PartnerCommissionEntry.product_id == Product.id)
                .filter(Sale.status == "confirmed")
            )

            if tenant_id is not None:
                rows = rows.filter(PartnerCommissionEntry.tenant_id == tenant_id)
            if scoped_branch_id is not None:
                rows = rows.filter(PartnerCommissionEntry.branch_id == scoped_branch_id)
            if date_from:
                rows = rows.filter(func.date(Sale.sale_date) >= date_from)
            if date_to:
                rows = rows.filter(func.date(Sale.sale_date) <= date_to)

            rows = rows.group_by(
                Product.name,
                Customer.name,
                PartnerCommissionEntry.percentage,
                Customer.id,
            ).all()

            for r in rows:
                total_qty = Decimal(str(r.total_qty or 0))
                total_revenue = Decimal(str(r.total_revenue or 0))
                partner_amount = Decimal(str(r.partner_share_amount or 0))
                avg_unit_price = (total_revenue / total_qty) if total_qty > 0 else Decimal("0")
                partners_data.append(
                    {
                        "product_name": r.product_name or "",
                        "partner_name": r.partner_name or "",
                        "percentage": r.percentage,
                        "avg_unit_price": avg_unit_price,
                        "total_qty": total_qty,
                        "total_revenue": total_revenue,
                        "partner_share_amount": partner_amount,
                    }
                )
                partner_share_totals[r.partner_id] = partner_share_totals.get(r.partner_id, Decimal("0")) + partner_amount
        else:
            partner_products = tenant_query(Product).filter(
                Product.is_active,
                Product.partner_shares.any(),
            )
            if tenant_id is not None:
                partner_products = partner_products.filter(Product.tenant_id == tenant_id)
            partner_products = partner_products.all()

            for product in partner_products:
                sales_query = (
                    tenant_query(SaleLine).join(Sale).filter(SaleLine.product_id == product.id, Sale.status == "confirmed")
                )
                if tenant_id is not None:
                    sales_query = sales_query.filter(SaleLine.tenant_id == tenant_id)
                if scoped_branch_id is not None:
                    sales_query = sales_query.filter(Sale.branch_id == scoped_branch_id)

                if date_from:
                    sales_query = sales_query.filter(func.date(Sale.sale_date) >= date_from)
                if date_to:
                    sales_query = sales_query.filter(func.date(Sale.sale_date) <= date_to)

                sales_lines = sales_query.all()

                total_revenue = sum(line.line_total for line in sales_lines)
                total_qty = sum(line.quantity for line in sales_lines)

                avg_unit_price = total_revenue / total_qty if total_qty > 0 else 0

                if total_revenue > 0:
                    for share in product.partner_shares:
                        percentage = Decimal(str(share.percentage))
                        partner_amount = total_revenue * (percentage / Decimal("100"))
                        partners_data.append(
                            {
                                "product_name": product.name,
                                "partner_name": share.partner_customer.name,
                                "percentage": share.percentage,
                                "avg_unit_price": avg_unit_price,
                                "total_qty": total_qty,
                                "total_revenue": total_revenue,
                                "partner_share_amount": partner_amount,
                            }
                        )

                        p_id = share.partner_customer.id
                        partner_share_totals[p_id] = partner_share_totals.get(p_id, Decimal("0")) + partner_amount

        # Find products linked to a merchant
        merchant_products = tenant_query(Product).filter(Product.merchant_customer_id.isnot(None), Product.is_active)
        if tenant_id is not None:
            merchant_products = merchant_products.filter(Product.tenant_id == tenant_id)
        merchant_products = merchant_products.all()

        merchants_data = []
        merchant_share_totals = {}

        for product in merchant_products:
            sales_query = (
                tenant_query(SaleLine).join(Sale).filter(SaleLine.product_id == product.id, Sale.status == "confirmed")
            )
            if tenant_id is not None:
                sales_query = sales_query.filter(SaleLine.tenant_id == tenant_id)
            if scoped_branch_id is not None:
                sales_query = sales_query.filter(Sale.branch_id == scoped_branch_id)

            if date_from:
                sales_query = sales_query.filter(func.date(Sale.sale_date) >= date_from)
            if date_to:
                sales_query = sales_query.filter(func.date(Sale.sale_date) <= date_to)

            sales_lines = sales_query.all()

            total_revenue = sum(line.line_total for line in sales_lines)
            total_qty = sum(line.quantity for line in sales_lines)

            # Calculate average unit price
            avg_unit_price = total_revenue / total_qty if total_qty > 0 else 0

            if total_revenue > 0:
                merchant_percentage = float(product.merchant_share or 100)
                merchant_amount = total_revenue * (Decimal(merchant_percentage) / 100)
                merchant = product.merchant_customer
                merchant_name = merchant.name if merchant else gettext("غير محدد")

                merchants_data.append(
                    {
                        "product_name": product.name,
                        "merchant_name": merchant_name,
                        "percentage": merchant_percentage,
                        "avg_unit_price": avg_unit_price,
                        "total_qty": total_qty,
                        "total_revenue": total_revenue,
                        "merchant_share_amount": merchant_amount,
                    }
                )

                m_id = merchant.id if merchant else product.merchant_customer_id
                if m_id is not None:
                    merchant_share_totals[m_id] = merchant_share_totals.get(m_id, Decimal("0")) + merchant_amount

        # --- 2. FINANCIAL SUMMARIES (Partners & Merchants) ---
        def get_financials(customer_type, share_totals_dict):
            customers = ReportsQueryService._scoped_customer_query().filter_by(customer_type=customer_type).all()
            if not customers:
                return []

            customer_ids = [c.id for c in customers]
            payment_scope = [
                Payment.customer_id.in_(customer_ids),
                payment_affects_balance(Payment),
            ]
            receipt_scope = [Receipt.customer_id.in_(customer_ids), payment_affects_balance(Receipt)]

            def _date_filters(q, col, d_from, d_to):
                if d_from:
                    q = q.filter(func.date(col) >= d_from)
                if d_to:
                    q = q.filter(func.date(col) <= d_to)
                return q

            def _tenant_branch_filters(q, tenant_col, branch_col):
                if tenant_id is not None:
                    q = q.filter(tenant_col == tenant_id)
                if scoped_branch_id is not None:
                    q = q.filter(branch_col == scoped_branch_id)
                return q

            paid_rows = (
                _tenant_branch_filters(
                    _date_filters(
                        db.session.query(
                            Payment.customer_id.label("cid"),
                            func.coalesce(func.sum(Payment.amount_aed), 0).label("amt"),
                        ).filter(
                            Payment.direction == "outgoing",
                            *payment_scope,
                        ),
                        Payment.payment_date,
                        date_from,
                        date_to,
                    ),
                    Payment.tenant_id,
                    Payment.branch_id,
                )
                .group_by(Payment.customer_id)
                .all()
            )
            total_paid_to_map = {r.cid: r.amt or Decimal("0") for r in paid_rows}

            received_rows = (
                _tenant_branch_filters(
                    _date_filters(
                        db.session.query(
                            Receipt.customer_id.label("cid"),
                            func.coalesce(func.sum(Receipt.amount_aed), 0).label("amt"),
                        ).filter(*receipt_scope),
                        Receipt.receipt_date,
                        date_from,
                        date_to,
                    ),
                    Receipt.tenant_id,
                    Receipt.branch_id,
                )
                .group_by(Receipt.customer_id)
                .all()
            )
            receipts_map = {r.cid: r.amt or Decimal("0") for r in received_rows}

            incoming_rows = (
                _tenant_branch_filters(
                    _date_filters(
                        db.session.query(
                            Payment.customer_id.label("cid"),
                            func.coalesce(func.sum(Payment.amount_aed), 0).label("amt"),
                        ).filter(
                            Payment.direction == "incoming",
                            *payment_scope,
                        ),
                        Payment.payment_date,
                        date_from,
                        date_to,
                    ),
                    Payment.tenant_id,
                    Payment.branch_id,
                )
                .group_by(Payment.customer_id)
                .all()
            )
            payment_in_map = {r.cid: r.amt or Decimal("0") for r in incoming_rows}

            summary_list = []
            for cust in customers:
                total_paid_to = total_paid_to_map.get(cust.id, Decimal("0"))
                total_receipts = receipts_map.get(cust.id, Decimal("0"))
                total_payment_in = payment_in_map.get(cust.id, Decimal("0"))
                total_received_from = total_receipts + total_payment_in

                total_share = share_totals_dict.get(cust.id, Decimal("0"))

                # For Partner/Merchant:
                # Balance (Net) = (Total Share + Total Received From) - Total Paid To
                # Assuming 'Share' is money they earned (credit to them).
                # 'Received From' is money they gave us (credit to them, or debt repayment?).
                # Usually: Balance = (Earnings + Deposits) - Withdrawals
                net_balance = (total_share + total_received_from) - total_paid_to

                # Only add if there's any activity
                if total_share > 0 or total_paid_to > 0 or total_received_from > 0:
                    summary_list.append(
                        {
                            "name": cust.name,
                            "total_share": total_share,
                            "paid_to": total_paid_to,
                            "received_from": total_received_from,
                            "net_balance": net_balance,
                        }
                    )
            return summary_list

        partners_summary = get_financials("partner", partner_share_totals)
        merchants_summary = get_financials("merchant", merchant_share_totals)

        # --- 3. SUPPLIERS SUMMARY ---
        suppliers = ReportsQueryService._scoped_supplier_query().all()
        suppliers_summary = []

        if suppliers:
            supplier_ids = [s.id for s in suppliers]
            supplier_tenant_ids = {s.tenant_id for s in suppliers}

            def _sup_date_filters(q, col, d_from, d_to):
                if d_from:
                    q = q.filter(func.date(col) >= d_from)
                if d_to:
                    q = q.filter(func.date(col) <= d_to)
                return q

            def _sup_branch_filter(q, branch_col):
                if scoped_branch_id is not None:
                    q = q.filter(branch_col == scoped_branch_id)
                return q

            sup_purchase_rows = (
                _sup_branch_filter(
                    _sup_date_filters(
                        db.session.query(
                            Purchase.supplier_id.label("sid"),
                            func.coalesce(func.sum(Purchase.amount_aed), 0).label("amt"),
                        ).filter(
                            Purchase.supplier_id.in_(supplier_ids),
                            Purchase.tenant_id.in_(supplier_tenant_ids),
                            Purchase.status == "confirmed",
                        ),
                        Purchase.purchase_date,
                        date_from,
                        date_to,
                    ),
                    Purchase.branch_id,
                )
                .group_by(Purchase.supplier_id)
                .all()
            )
            purchases_map = {r.sid: r.amt or Decimal("0") for r in sup_purchase_rows}

            sup_paid_rows = (
                _sup_branch_filter(
                    _sup_date_filters(
                        db.session.query(
                            Payment.supplier_id.label("sid"),
                            func.coalesce(func.sum(Payment.amount_aed), 0).label("amt"),
                        ).filter(
                            Payment.supplier_id.in_(supplier_ids),
                            Payment.tenant_id.in_(supplier_tenant_ids),
                            Payment.direction == "outgoing",
                            payment_affects_balance(Payment),
                        ),
                        Payment.payment_date,
                        date_from,
                        date_to,
                    ),
                    Payment.branch_id,
                )
                .group_by(Payment.supplier_id)
                .all()
            )
            paid_map = {r.sid: r.amt or Decimal("0") for r in sup_paid_rows}

            sup_refund_rows = (
                _sup_branch_filter(
                    _sup_date_filters(
                        db.session.query(
                            Payment.supplier_id.label("sid"),
                            func.coalesce(func.sum(Payment.amount_aed), 0).label("amt"),
                        ).filter(
                            Payment.supplier_id.in_(supplier_ids),
                            Payment.tenant_id.in_(supplier_tenant_ids),
                            Payment.direction == "incoming",
                            payment_affects_balance(Payment),
                        ),
                        Payment.payment_date,
                        date_from,
                        date_to,
                    ),
                    Payment.branch_id,
                )
                .group_by(Payment.supplier_id)
                .all()
            )
            refunds_map = {r.sid: r.amt or Decimal("0") for r in sup_refund_rows}

            for sup in suppliers:
                total_purchases = purchases_map.get(sup.id, Decimal("0"))
                total_paid_to = paid_map.get(sup.id, Decimal("0"))
                total_refunds = refunds_map.get(sup.id, Decimal("0"))

                # Balance = Purchases - (Paid - Refunds)
                # Or: Purchases - Net Paid
                net_paid = total_paid_to - total_refunds
                balance_due = total_purchases - net_paid

                if total_purchases > 0 or total_paid_to > 0 or total_refunds > 0:
                    suppliers_summary.append(
                        {
                            "name": sup.name,
                            "total_purchases": total_purchases,
                            "paid_to": total_paid_to,
                            "received_from": total_refunds,
                            "balance_due": balance_due,
                        }
                    )

        return {
            "partners_data": partners_data,
            "merchants_data": merchants_data,
            "partners_summary": partners_summary,
            "merchants_summary": merchants_summary,
            "suppliers_summary": suppliers_summary,
        }

    # ------------------------------------------------------------------
    # Sales report
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_sales_report(tenant_id, scoped_branch_id, date_from, date_to, customer_id, seller_id, seller_user_id=None):
        from models import Sale

        query = tenant_query(Sale).filter_by(status="confirmed")
        if tenant_id is not None:
            query = query.filter(Sale.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            query = query.filter(Sale.branch_id == scoped_branch_id)

        if date_from:
            query = query.filter(func.date(Sale.sale_date) >= date_from)

        if date_to:
            query = query.filter(func.date(Sale.sale_date) <= date_to)

        if customer_id:
            query = query.filter_by(customer_id=customer_id)

        if seller_id:
            query = query.filter_by(seller_id=seller_id)
        elif seller_user_id:
            query = query.filter_by(seller_id=seller_user_id)

        return query.order_by(Sale.sale_date.desc()).limit(5000).all()

    @staticmethod
    def fetch_report_customers(tenant_id, scoped_branch_id):
        from models import Customer, Sale

        customers_query = Customer.query
        if tenant_id is not None:
            customers_query = customers_query.filter(Customer.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            customer_ids = select(Sale.customer_id).where(Sale.branch_id == scoped_branch_id, Sale.customer_id.isnot(None))
            customers_query = customers_query.filter(Customer.id.in_(customer_ids))
        return customers_query.order_by(Customer.name).limit(500).all()

    @staticmethod
    def fetch_report_sellers(scoped_branch_id):
        from models import Sale, User
        from utils.tenanting import scoped_user_query

        sellers_query = scoped_user_query(active_only=True)
        if scoped_branch_id is not None:
            seller_ids = select(Sale.seller_id).where(Sale.branch_id == scoped_branch_id, Sale.seller_id.isnot(None))
            sellers_query = sellers_query.filter(User.id.in_(seller_ids))
        return sellers_query.order_by(User.username).limit(500).all()

    # ------------------------------------------------------------------
    # Purchases report
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_purchases_report(tenant_id, scoped_branch_id, date_from, date_to, supplier_id):
        from models import Purchase

        query = tenant_query(Purchase).filter_by(status="confirmed")
        if tenant_id is not None:
            query = query.filter(Purchase.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            query = query.filter(Purchase.branch_id == scoped_branch_id)

        if date_from:
            query = query.filter(func.date(Purchase.purchase_date) >= date_from)

        if date_to:
            query = query.filter(func.date(Purchase.purchase_date) <= date_to)

        if supplier_id:
            query = query.filter_by(supplier_id=supplier_id)

        return query.order_by(Purchase.purchase_date.desc()).limit(5000).all()

    @staticmethod
    def fetch_purchases_payments(tenant_id, scoped_branch_id, date_from, date_to, supplier_id):
        """Supplier payments grouped FIFO-style per supplier, ordered by date asc."""
        from decimal import Decimal as Dec

        from models import Payment, Supplier

        supplier_payments = {}
        pmt_query = tenant_query(Payment).filter(
            Payment.direction == "outgoing",
            Payment.supplier_id.isnot(None),
            payment_affects_balance(Payment),
        )
        if tenant_id is not None:
            pmt_query = pmt_query.filter(Payment.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            pmt_query = pmt_query.filter(Payment.branch_id == scoped_branch_id)
        if date_from:
            pmt_query = pmt_query.filter(func.date(Payment.payment_date) >= date_from)
        if date_to:
            pmt_query = pmt_query.filter(func.date(Payment.payment_date) <= date_to)
        if supplier_id:
            pmt_query = pmt_query.filter(Payment.supplier_id == supplier_id)

        for pmt in pmt_query.order_by(Payment.payment_date.asc()).all():
            sid = pmt.supplier_id
            if sid not in supplier_payments:
                supplier_payments[sid] = []
            supplier_payments[sid].append(Dec(str(pmt.amount_aed or 0)))

        # Apply FIFO per supplier
        remaining_payments = {}
        for sid, amounts in supplier_payments.items():
            remaining_payments[sid] = sum(amounts)
        return supplier_payments, remaining_payments

    @staticmethod
    def list_active_suppliers_for_filter():
        from models import Supplier

        return ReportsQueryService._scoped_supplier_query().filter(Supplier.is_active).order_by(Supplier.name).all()

    # ------------------------------------------------------------------
    # Receivables aging
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_receivables_sales(tenant_id, scoped_branch_id, customer_id):
        from models import Sale

        all_sales = tenant_query(Sale).filter(Sale.status == "confirmed")
        if tenant_id is not None:
            all_sales = all_sales.filter(Sale.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            all_sales = all_sales.filter(Sale.branch_id == scoped_branch_id)
        if customer_id:
            all_sales = all_sales.filter(Sale.customer_id == customer_id)
        return all_sales.order_by(Sale.sale_date.desc()).limit(5000).all()

    # ------------------------------------------------------------------
    # Inventory reconciliation warehouses
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_inventory_reconciliation_warehouses(branch_id, user):
        from models import Warehouse as WarehouseModel

        warehouses_query = tenant_query(WarehouseModel).filter_by(is_active=True)
        if branch_id is not None:
            warehouses_query = warehouses_query.filter(WarehouseModel.branch_id == branch_id)
        else:
            from utils.branching import get_accessible_warehouse_ids

            accessible_ids = get_accessible_warehouse_ids(user)
            if accessible_ids:
                warehouses_query = warehouses_query.filter(WarehouseModel.id.in_(accessible_ids))
            elif not user.is_admin():
                warehouses_query = warehouses_query.filter(WarehouseModel.id < 0)
        return warehouses_query.order_by(WarehouseModel.name).all()

    @staticmethod
    def find_active_warehouse(warehouse_id):
        from models import Warehouse

        return Warehouse.query.filter_by(id=warehouse_id, is_active=True).first()

    # ------------------------------------------------------------------
    # Inventory report (page + export share identical map/product queries)
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_inventory_warehouses(tenant_id, branch_id, user, ordered=True):
        from models import Warehouse
        from utils.branching import get_accessible_warehouse_ids

        warehouses_query = tenant_query(Warehouse).filter_by(is_active=True)
        if tenant_id is not None:
            warehouses_query = warehouses_query.filter(Warehouse.tenant_id == tenant_id)
        if branch_id is not None:
            warehouses_query = warehouses_query.filter(Warehouse.branch_id == branch_id)
        else:
            accessible_ids = get_accessible_warehouse_ids(user)
            if accessible_ids:
                warehouses_query = warehouses_query.filter(Warehouse.id.in_(accessible_ids))
            elif not user.is_admin():
                warehouses_query = warehouses_query.filter(Warehouse.id < 0)
        if ordered:
            return warehouses_query.order_by(Warehouse.is_main.desc(), Warehouse.name).all()
        return warehouses_query.all()

    @staticmethod
    def build_stock_maps(warehouse_ids, tenant_id, in_date_from, in_date_to, out_date_from, out_date_to):
        """Bulk stock aggregates: one grouped query per bucket (no N+1)."""
        from models import StockMovement

        stock_query = db.session.query(
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity), 0).label("qty"),
        ).filter(StockMovement.warehouse_id.in_(warehouse_ids))
        if tenant_id is not None:
            stock_query = stock_query.filter(StockMovement.tenant_id == tenant_id)
        stock_map = dict(stock_query.group_by(StockMovement.product_id).all())

        in_query = db.session.query(
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity), 0).label("qty"),
        ).filter(StockMovement.warehouse_id.in_(warehouse_ids), StockMovement.quantity > 0)
        if tenant_id is not None:
            in_query = in_query.filter(StockMovement.tenant_id == tenant_id)
        if in_date_from:
            in_query = in_query.filter(func.date(StockMovement.created_at) >= in_date_from)
        if in_date_to:
            in_query = in_query.filter(func.date(StockMovement.created_at) <= in_date_to)
        in_map = dict(in_query.group_by(StockMovement.product_id).all())

        out_query = db.session.query(
            StockMovement.product_id,
            func.coalesce(func.sum(-StockMovement.quantity), 0).label("qty"),
        ).filter(StockMovement.warehouse_id.in_(warehouse_ids), StockMovement.quantity < 0)
        if tenant_id is not None:
            out_query = out_query.filter(StockMovement.tenant_id == tenant_id)
        if out_date_from:
            out_query = out_query.filter(func.date(StockMovement.created_at) >= out_date_from)
        if out_date_to:
            out_query = out_query.filter(func.date(StockMovement.created_at) <= out_date_to)
        out_map = dict(out_query.group_by(StockMovement.product_id).all())

        sold_query = db.session.query(
            StockMovement.product_id,
            func.coalesce(func.sum(-StockMovement.quantity), 0).label("qty"),
        ).filter(
            StockMovement.warehouse_id.in_(warehouse_ids),
            StockMovement.movement_type == "sale",
            StockMovement.quantity < 0,
        )
        if tenant_id is not None:
            sold_query = sold_query.filter(StockMovement.tenant_id == tenant_id)
        if out_date_from:
            sold_query = sold_query.filter(func.date(StockMovement.created_at) >= out_date_from)
        if out_date_to:
            sold_query = sold_query.filter(func.date(StockMovement.created_at) <= out_date_to)
        sold_map = dict(sold_query.group_by(StockMovement.product_id).all())

        return stock_map, in_map, out_map, sold_map

    @staticmethod
    def fetch_inventory_products(category_id, include_zero, stock_map):
        from models import Product

        query = tenant_query(Product).filter_by(is_active=True)
        if category_id:
            query = query.filter_by(category_id=category_id)

        if not include_zero:
            product_ids = [pid for pid, qty in stock_map.items() if (qty or 0) != 0]
            query = query.filter(Product.id.in_(product_ids)) if product_ids else query.filter(Product.id < 0)

        return query.order_by(Product.name).all()

    # ------------------------------------------------------------------
    # Entity search
    # ------------------------------------------------------------------
    @staticmethod
    def search_entities(query_text, entity_type):
        from models import Customer, Supplier

        results = []

        if entity_type == "supplier":
            suppliers = (
                ReportsQueryService._scoped_supplier_query()
                .filter(
                    db.or_(
                        Supplier.name.ilike(f"%{query_text}%"),
                        Supplier.phone.ilike(f"%{query_text}%"),
                    )
                )
                .limit(10)
                .all()
            )
            for s in suppliers:
                results.append({"id": s.id, "name": s.name, "phone": s.phone, "type": "supplier"})

        else:  # customer, partner, merchant
            q_filter = ReportsQueryService._scoped_customer_query().filter(
                db.or_(Customer.name.ilike(f"%{query_text}%"), Customer.phone.ilike(f"%{query_text}%"))
            )

            if entity_type == "partner":
                q_filter = q_filter.filter_by(customer_type="partner")
            elif entity_type == "merchant":
                q_filter = q_filter.filter_by(customer_type="merchant")

            customers = q_filter.limit(10).all()
            for c in customers:
                results.append({"id": c.id, "name": c.name, "phone": c.phone, "type": c.customer_type})

        return results

    # ------------------------------------------------------------------
    # Entity report fragment (supplier / customer detail)
    # ------------------------------------------------------------------
    @staticmethod
    def build_supplier_fragment_data(record_id, tenant_id, scoped_branch_id):
        from datetime import datetime as dt

        from models import Payment, Product, Purchase, PurchaseLine

        context: dict[str, Any] = {
            "products": [],
            "invoices": [],
            "transactions": [],
        }

        # Products (Purchased)
        p_lines = (
            db.session.query(
                Product.name,
                func.sum(PurchaseLine.quantity).label("qty"),
                func.sum(PurchaseLine.line_total).label("total"),
                func.max(Purchase.purchase_date).label("last_date"),
            )
            .join(Purchase)
            .join(Product)
            .filter(Purchase.supplier_id == record_id, Purchase.status == "confirmed")
        )
        if tenant_id is not None:
            p_lines = p_lines.filter(Purchase.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            p_lines = p_lines.filter(Purchase.branch_id == scoped_branch_id)
        p_lines = p_lines.group_by(Product.name).all()

        context["products"] = [
            {
                "name": p.name,
                "quantity": p.qty,
                "total": p.total,
                "last_date": (p.last_date.strftime("%Y-%m-%d") if p.last_date else "-"),
            }
            for p in p_lines
        ]

        # Invoices (Purchases)
        purchases = Purchase.query.filter_by(supplier_id=record_id)
        if tenant_id is not None:
            purchases = purchases.filter(Purchase.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            purchases = purchases.filter(Purchase.branch_id == scoped_branch_id)
        purchases = purchases.order_by(Purchase.purchase_date.desc()).all()

        fifo_purchases = sorted(purchases, key=lambda p: (p.purchase_date or dt.min, p.id or 0))

        supplier_payments_base = Payment.query.filter(
            Payment.supplier_id == record_id,
            Payment.direction == "outgoing",
            payment_affects_balance(Payment),
        )
        if tenant_id is not None:
            supplier_payments_base = supplier_payments_base.filter(Payment.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            supplier_payments_base = supplier_payments_base.filter(Payment.branch_id == scoped_branch_id)

        direct_payments = supplier_payments_base.filter(Payment.purchase_id.isnot(None)).all()
        unallocated_payments = supplier_payments_base.filter(Payment.purchase_id.is_(None)).all()
        has_direct_allocation = len(direct_payments) > 0

        if has_direct_allocation:
            paid_map = {}
            for pymt in direct_payments:
                pid = pymt.purchase_id
                if pid:
                    paid_map[pid] = paid_map.get(pid, Decimal("0")) + Decimal(str(pymt.amount_aed or 0))
            unallocated_credit = sum(Decimal(str(p.amount_aed or 0)) for p in unallocated_payments)
        else:
            total_paid_fifo = Decimal(
                str(supplier_payments_base.with_entities(func.sum(Payment.amount_aed)).scalar() or 0)
            )
            remaining_paid = total_paid_fifo
            paid_map = {}
            for p in fifo_purchases:
                amount = Decimal(str(p.amount_aed or 0))
                allocated = min(amount, remaining_paid) if remaining_paid > 0 else Decimal("0")
                paid_map[p.id] = allocated
                remaining_paid = max(Decimal("0"), remaining_paid - allocated)
            unallocated_credit = Decimal("0")

        context["invoices"] = [
            {
                "number": p.purchase_number,
                "date": p.purchase_date.strftime("%Y-%m-%d"),
                "status": p.status,
                "amount": p.amount_aed or 0,
                "paid": paid_map.get(p.id, Decimal("0")),
                "balance": (Decimal(str(p.amount_aed or 0)) - paid_map.get(p.id, Decimal("0"))),
            }
            for p in purchases
        ]
        context["allocation_exact"] = has_direct_allocation
        context["unallocated_supplier_credit"] = unallocated_credit

        payments = Payment.query.filter(Payment.supplier_id == record_id, payment_affects_balance(Payment))
        if tenant_id is not None:
            payments = payments.filter(Payment.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            payments = payments.filter(Payment.branch_id == scoped_branch_id)
        payments = payments.order_by(Payment.payment_date.desc()).all()
        total_purchases_amount = sum((p.amount_aed or 0) for p in purchases)
        total_payments_amount = sum((p.amount_aed or 0) for p in payments if p.direction == "outgoing")

        # Balance
        context["balance"] = total_purchases_amount - total_payments_amount
        context["balance_label"] = gettext("مستحق للمورد")
        context["transactions"] = [
            {
                "number": p.payment_number,
                "type": "out",  # Payment out
                "date": p.payment_date.strftime("%Y-%m-%d"),
                "amount": p.amount_aed,
                "method": p.payment_method,
                "notes": p.notes or "-",
            }
            for p in payments
        ]
        return context

    @staticmethod
    def build_customer_fragment_data(record_id, customer_type, tenant_id, scoped_branch_id):
        from flask_babel import gettext as _gettext

        from models import Payment, Product, ProductPartner, Sale, SaleLine
        from models.receipt import Receipt

        context: dict[str, Any] = {
            "products": [],
            "invoices": [],
            "transactions": [],
        }

        # Balance calculation (Receivables/Payables)
        # Sales (He took goods) + Payments Out (He took money) - Receipts (He gave money)
        total_sales_query = db.session.query(func.sum(Sale.amount_aed)).filter(
            Sale.customer_id == record_id, Sale.status == "confirmed"
        )
        total_receipts_query = db.session.query(func.sum(Receipt.amount_aed)).filter(
            Receipt.customer_id == record_id, payment_affects_balance(Receipt)
        )
        # Payments made TO customer (e.g. returns/share/drawings)
        total_payments_query = db.session.query(func.sum(Payment.amount_aed)).filter(
            Payment.customer_id == record_id,
            Payment.direction == "outgoing",
            payment_affects_balance(Payment),
        )
        if tenant_id is not None:
            total_sales_query = total_sales_query.filter(Sale.tenant_id == tenant_id)
            total_receipts_query = total_receipts_query.filter(Receipt.tenant_id == tenant_id)
            total_payments_query = total_payments_query.filter(Payment.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            total_sales_query = total_sales_query.filter(Sale.branch_id == scoped_branch_id)
            total_receipts_query = total_receipts_query.filter(Receipt.branch_id == scoped_branch_id)
            total_payments_query = total_payments_query.filter(Payment.branch_id == scoped_branch_id)
        total_sales = total_sales_query.scalar() or 0
        total_receipts = total_receipts_query.scalar() or 0
        total_payments_to = total_payments_query.scalar() or 0

        context["balance"] = (total_sales + total_payments_to) - total_receipts  # Positive means they owe us
        context["balance_label"] = _gettext("مستحق لنا")
        if context["balance"] < 0:
            context["balance"] = abs(context["balance"])
            context["balance_label"] = _gettext("مستحق للعميل")

        # Products (Sold) - Products the customer BOUGHT
        s_lines = (
            db.session.query(
                Product.name,
                func.sum(SaleLine.quantity).label("qty"),
                func.sum(SaleLine.line_total).label("total"),
                func.max(Sale.sale_date).label("last_date"),
            )
            .join(Sale)
            .join(Product)
            .filter(Sale.customer_id == record_id, Sale.status == "confirmed")
        )
        if tenant_id is not None:
            s_lines = s_lines.filter(Sale.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            s_lines = s_lines.filter(Sale.branch_id == scoped_branch_id)
        s_lines = s_lines.group_by(Product.name).all()

        context["products"] = [
            {
                "name": p.name,
                "quantity": p.qty,
                "total": p.total,
                "last_date": (p.last_date.strftime("%Y-%m-%d") if p.last_date else "-"),
            }
            for p in s_lines
        ]

        # IF PARTNER: Fetch products they have a share in (Products they EARN from)
        if customer_type == "partner":
            shared_products_query = (
                db.session.query(
                    Product.name,
                    ProductPartner.percentage,
                    func.sum(SaleLine.quantity).label("qty"),
                    func.sum(SaleLine.line_total).label("total_sales"),
                    func.max(Sale.sale_date).label("last_date"),
                )
                .join(ProductPartner, Product.id == ProductPartner.product_id)
                .join(SaleLine, SaleLine.product_id == Product.id)
                .join(Sale, Sale.id == SaleLine.sale_id)
                .filter(
                    ProductPartner.partner_customer_id == record_id,
                    Sale.status == "confirmed",
                )
            )
            if tenant_id is not None:
                shared_products_query = shared_products_query.filter(Sale.tenant_id == tenant_id)
            if scoped_branch_id is not None:
                shared_products_query = shared_products_query.filter(Sale.branch_id == scoped_branch_id)
            shared_products_query = shared_products_query.group_by(Product.name, ProductPartner.percentage).all()

            for sp in shared_products_query:
                share_amount = sp.total_sales * (sp.percentage / 100)
                context["products"].append(
                    {
                        "name": f"{sp.name} (Share: {sp.percentage}%)",
                        "quantity": sp.qty,
                        "total": share_amount,
                        "last_date": (sp.last_date.strftime("%Y-%m-%d") if sp.last_date else "-"),
                    }
                )

        # IF MERCHANT: Fetch products they own (Products they EARN from)
        if customer_type == "merchant":
            merchant_products_query = (
                db.session.query(
                    Product.name,
                    Product.merchant_share,
                    func.sum(SaleLine.quantity).label("qty"),
                    func.sum(SaleLine.line_total).label("total_sales"),
                    func.max(Sale.sale_date).label("last_date"),
                )
                .join(SaleLine, SaleLine.product_id == Product.id)
                .join(Sale, Sale.id == SaleLine.sale_id)
                .filter(
                    Product.merchant_customer_id == record_id,
                    Sale.status == "confirmed",
                )
            )
            if tenant_id is not None:
                merchant_products_query = merchant_products_query.filter(Sale.tenant_id == tenant_id)
            if scoped_branch_id is not None:
                merchant_products_query = merchant_products_query.filter(Sale.branch_id == scoped_branch_id)
            merchant_products_query = merchant_products_query.group_by(Product.name, Product.merchant_share).all()

            for mp in merchant_products_query:
                share_pct = mp.merchant_share or 100
                share_amount = mp.total_sales * (share_pct / 100)
                context["products"].append(
                    {
                        "name": f"{mp.name} (Merchant: {share_pct}%)",
                        "quantity": mp.qty,
                        "total": share_amount,
                        "last_date": (mp.last_date.strftime("%Y-%m-%d") if mp.last_date else "-"),
                    }
                )

        # Invoices (Sales)
        sales = Sale.query.filter_by(customer_id=record_id)
        if tenant_id is not None:
            sales = sales.filter(Sale.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            sales = sales.filter(Sale.branch_id == scoped_branch_id)
        sales = sales.order_by(Sale.sale_date.desc()).all()
        context["invoices"] = [
            {
                "number": s.sale_number,
                "date": s.sale_date.strftime("%Y-%m-%d"),
                "status": s.status,
                "amount": s.amount_aed or 0,
                "paid": s.paid_amount_aed or 0,
                "balance": (s.amount_aed or 0) - (s.paid_amount_aed or 0),
            }
            for s in sales
        ]

        receipts = Receipt.query.filter(Receipt.customer_id == record_id, payment_affects_balance(Receipt))
        payments_out = Payment.query.filter(
            Payment.customer_id == record_id, Payment.direction == "outgoing", payment_affects_balance(Payment)
        )
        if tenant_id is not None:
            receipts = receipts.filter(Receipt.tenant_id == tenant_id)
            payments_out = payments_out.filter(Payment.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            receipts = receipts.filter(Receipt.branch_id == scoped_branch_id)
            payments_out = payments_out.filter(Payment.branch_id == scoped_branch_id)
        receipts = receipts.all()
        payments_out = payments_out.all()

        all_trans = []
        for r in receipts:
            all_trans.append(
                {
                    "number": r.receipt_number,
                    "type": "in",  # Money In
                    "date": r.receipt_date,
                    "amount": r.amount_aed,
                    "method": r.payment_method,
                    "notes": _gettext("قبض"),
                }
            )
        for p in payments_out:
            all_trans.append(
                {
                    "number": p.payment_number,
                    "type": "out",  # Money Out
                    "date": p.payment_date,
                    "amount": p.amount_aed,
                    "method": p.payment_method,
                    "notes": p.notes or _gettext("دفع"),
                }
            )

        all_trans.sort(key=lambda x: x["date"], reverse=True)
        for t in all_trans:
            t["date"] = t["date"].strftime("%Y-%m-%d")

        context["transactions"] = all_trans
        return context

    # ------------------------------------------------------------------
    # Top selling
    # ------------------------------------------------------------------
    @staticmethod
    def fetch_top_selling_products(date_from, date_to, tenant_id, scoped_branch_id, limit):
        from models import Product, Sale, SaleLine

        query = (
            db.session.query(
                Product.id,
                Product.name,
                func.sum(SaleLine.quantity).label("total_quantity"),
                func.sum(SaleLine.line_total).label("total_sales"),
            )
            .join(SaleLine, Product.id == SaleLine.product_id)
            .join(Sale, SaleLine.sale_id == Sale.id)
            .filter(Sale.status == "confirmed")
        )
        if tenant_id is not None:
            query = query.filter(Sale.tenant_id == tenant_id)
        if scoped_branch_id is not None:
            query = query.filter(Sale.branch_id == scoped_branch_id)

        if date_from:
            query = query.filter(func.date(Sale.sale_date) >= date_from)

        if date_to:
            query = query.filter(func.date(Sale.sale_date) <= date_to)

        return query.group_by(Product.id, Product.name).order_by(func.sum(SaleLine.quantity).desc()).limit(limit).all()
