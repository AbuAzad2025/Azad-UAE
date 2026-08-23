"""
VaultQueryService — read-only query layer for payment-vault routes.

Pure read-fetch helpers. Every method returns model objects / query
terminals (lists, scalars, pagination) so routes stay query-free.
Uses flush-free reads only — callers own all transactions.
"""


class VaultQueryService:
    @staticmethod
    def find_active_api_key(raw_key):
        from models import APIKey

        return APIKey.query.filter_by(key=raw_key, is_active=True).first()

    # ── Donation ledger (platform scope: tenant_id NULL) ──

    @staticmethod
    def list_platform_records(tid=None, transaction_type=None):
        from models import Donation

        query = Donation.query.filter_by(tenant_id=tid)
        if transaction_type is not None:
            query = query.filter_by(transaction_type=transaction_type)
        return query.all()

    @staticmethod
    def list_platform_records_desc(tid=None):
        from models import Donation

        return Donation.query.filter_by(tenant_id=tid).order_by(Donation.created_at.desc()).all()

    @staticmethod
    def recent_platform_records(tid=None, transaction_type=None, limit=5):
        from models import Donation

        return (
            Donation.query.filter_by(tenant_id=tid, transaction_type=transaction_type)
            .order_by(Donation.created_at.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def donations_overview(tid, status_filter, crypto_filter, search_query, page, per_page):
        """Paginated donation listing plus aggregate counters for one base query."""
        from extensions import db
        from models import Donation

        query = Donation.query.filter_by(tenant_id=tid, transaction_type="donation")
        if status_filter:
            query = query.filter_by(status=status_filter)
        if crypto_filter:
            query = query.filter_by(crypto_type=crypto_filter)
        if search_query:
            query = query.filter(
                db.or_(
                    Donation.donor_name.ilike(f"%{search_query}%"),
                    Donation.donor_email.ilike(f"%{search_query}%"),
                )
            )
        pagination = query.order_by(Donation.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        completed_count = query.filter(Donation.status == "completed").count()
        pending_count = query.filter(Donation.status == "pending").count()
        total_amount = float(query.with_entities(db.func.coalesce(db.func.sum(Donation.amount_usd), 0)).scalar() or 0)
        return pagination, completed_count, pending_count, total_amount

    @staticmethod
    def donation_monthly_aggregates(tid, start_of_window):
        """(year, month, transaction_type, total) rows since start_of_window."""
        from sqlalchemy import extract, func

        from extensions import db
        from models import Donation

        year_col = extract("year", Donation.created_at)
        month_col = extract("month", Donation.created_at)
        return (
            db.session.query(
                year_col.label("y"),
                month_col.label("m"),
                Donation.transaction_type,
                func.sum(Donation.amount_usd).label("total"),
            )
            .filter(Donation.tenant_id == tid, Donation.created_at >= start_of_window)
            .group_by(year_col, month_col, Donation.transaction_type)
            .all()
        )

    @staticmethod
    def platform_package_purchase_counts(tid, slugs):
        """Per-slug purchase counts, preserving input order."""
        from models import Donation

        return [
            Donation.query.filter_by(tenant_id=tid, transaction_type="purchase", package=slug).count()
            for slug in slugs
        ]

    @staticmethod
    def find_donation_by_transaction_hash(transaction_hash):
        from models import Donation

        return Donation.query.filter_by(transaction_hash=transaction_hash).first()

    @staticmethod
    def find_purchase_donation_by_email(customer_email, tid=None):
        from models import Donation

        return Donation.query.filter_by(
            tenant_id=tid,
            customer_email=customer_email,
            transaction_type="purchase",
        ).first()

    @staticmethod
    def get_platform_donation_or_404(donation_id, tid=None):
        from models import Donation

        return Donation.query.filter_by(id=donation_id, tenant_id=tid).first_or_404()

    @staticmethod
    def get_any_donation_or_404(donation_id):
        from models import Donation

        return Donation.query.filter_by(id=donation_id).first_or_404()

    @staticmethod
    def pending_platform_donations_count(tid=None):
        from models import Donation

        return Donation.query.filter_by(tenant_id=tid, status="pending").count()

    # ── Packages ──

    @staticmethod
    def list_packages_ordered():
        from models import Package

        return Package.query.order_by(Package.sort_order.asc()).all()

    @staticmethod
    def package_purchase_counts_by_slug(slugs):
        """Purchase counts joined through Package, preserving input order."""
        from models import Package, PackagePurchase

        return [PackagePurchase.query.join(Package).filter(Package.slug == slug).count() for slug in slugs]

    @staticmethod
    def find_package_by_slug(slug):
        from models import Package

        return Package.query.filter_by(slug=slug).first()

    @staticmethod
    def get_package_or_404(package_id):
        from models import Package

        return Package.query.get_or_404(package_id)

    @staticmethod
    def get_package_by_id(package_id):
        from extensions import db
        from models import Package

        return db.session.get(Package, package_id)

    # ── Package purchases ──

    @staticmethod
    def purchases_page(page, per_page, status_filter=""):
        from models import PackagePurchase

        query = PackagePurchase.query
        if status_filter:
            query = query.filter_by(payment_status=status_filter)
        return query.order_by(PackagePurchase.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def list_all_purchases():
        from models import PackagePurchase

        return PackagePurchase.query.all()

    @staticmethod
    def list_purchases_desc():
        from models import PackagePurchase

        return PackagePurchase.query.order_by(PackagePurchase.created_at.desc()).all()

    @staticmethod
    def get_purchase_or_404(purchase_id):
        from models import PackagePurchase

        return PackagePurchase.query.get_or_404(purchase_id)

    @staticmethod
    def purchases_for_package(package_id):
        from models import PackagePurchase

        return PackagePurchase.query.filter_by(package_id=package_id).all()

    @staticmethod
    def purchases_paginated_v2(page, per_page, status="", package_id=None, search="", sort_by="created_at", order="desc"):
        from extensions import db
        from models import PackagePurchase

        query = PackagePurchase.query
        if status:
            query = query.filter_by(payment_status=status)
        if package_id:
            query = query.filter_by(package_id=package_id)
        if search:
            query = query.filter(
                db.or_(
                    PackagePurchase.customer_name.ilike(f"%{search}%"),
                    PackagePurchase.customer_email.ilike(f"%{search}%"),
                )
            )
        if hasattr(PackagePurchase, sort_by):
            column = getattr(PackagePurchase, sort_by)
            query = query.order_by(column.asc()) if order == "asc" else query.order_by(column.desc())
        return query.paginate(page=page, per_page=per_page, error_out=False)

    @staticmethod
    def donations_paginated_v2(tid, page, per_page, status="", search=""):
        from extensions import db
        from models import Donation

        query = Donation.query.filter_by(tenant_id=tid, transaction_type="donation")
        if status:
            query = query.filter_by(status=status)
        if search:
            query = query.filter(
                db.or_(
                    Donation.donor_name.ilike(f"%{search}%"),
                    Donation.donor_email.ilike(f"%{search}%"),
                )
            )
        return query.order_by(Donation.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    # ── Cards ──

    @staticmethod
    def list_cards():
        from models import CardPayment
        from utils.tenanting import tenant_query

        return tenant_query(CardPayment).order_by(CardPayment.created_at.desc()).all()

    @staticmethod
    def get_card_or_404(card_id):
        from models import CardPayment
        from utils.tenanting import tenant_get_or_404

        return tenant_get_or_404(CardPayment, card_id)
