"""storefront hardening: tenant-scoped indexes, money/check constraints, platform locks

Storefront (online-store) hardening follow-up:

* Composite tenant-leading indexes on the hot storefront paths
  (reviews, wishlist, saved payments, variants, stock alerts, abandoned
  carts, coupons).
* ``shop_stock_alerts`` unique scope widens from (email, product) to
  (tenant, email, product) with duplicate backfill, so two tenants can
  alert the same address independently.
* ``shop_loyalty`` enforces the documented 1:1 header per account
  (duplicate backfill keeps the oldest row).
* ``shop_reviews``: rating 1-5 CHECK, ``is_approved`` NOT NULL backfill.
* ``store_coupons``: percent/amount/min-order sanity CHECKs.
* ``tenant_stores``: ``is_enabled`` server default + availability index;
  ``low_stock_threshold`` NULL backfill + NOT NULL + default.
* New columns: ``store_payment_methods.platform_disabled`` (owner
  force-OFF per payment method), ``shop_abandoned_carts.session_key``
  (per-guest snapshot keying).

SQLite-safe via batch_alter_table; every step guarded by table/column
existence checks so partial/provisioned databases keep working.

Revision ID: f4a9c2e71b05
Revises: c3d4e5f6a7b8
Create Date: 2026-09-15 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f4a9c2e71b05"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return name in insp.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in [c["name"] for c in insp.get_columns(table)]


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    try:
        return any(ix["name"] == name for ix in insp.get_indexes(table))
    except Exception:
        return False


def _create_index(name, table, columns):
    if _table_exists(table) and not _index_exists(table, name):
        op.create_index(name, table, columns)


def _drop_index(name, table):
    if _table_exists(table) and _index_exists(table, name):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(name)


def _add_check(table, name, predicate):
    if _table_exists(table):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_check_constraint(name, sa.text(predicate))


def _drop_check(table, name):
    if _table_exists(table):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(name, type_="check")


def _add_unique(table, name, columns):
    if _table_exists(table):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.create_unique_constraint(name, columns)


def _drop_unique(table, name):
    if _table_exists(table):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(name, type_="unique")


def upgrade():
    # ── 1. New columns ──────────────────────────────────────────────
    if _table_exists("store_payment_methods") and not _column_exists("store_payment_methods", "platform_disabled"):
        with op.batch_alter_table("store_payment_methods", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "platform_disabled",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                )
            )
    if _table_exists("shop_abandoned_carts") and not _column_exists("shop_abandoned_carts", "session_key"):
        with op.batch_alter_table("shop_abandoned_carts", schema=None) as batch_op:
            batch_op.add_column(sa.Column("session_key", sa.String(64), nullable=True))

    # ── 2. Backfills before NOT NULL ─────────────────────────────────
    if _table_exists("tenant_stores") and _column_exists("tenant_stores", "low_stock_threshold"):
        op.execute(
            sa.text("UPDATE tenant_stores SET low_stock_threshold = 5.0 WHERE low_stock_threshold IS NULL")
        )
    if _table_exists("shop_reviews") and _column_exists("shop_reviews", "is_approved"):
        op.execute(sa.text("UPDATE shop_reviews SET is_approved = false WHERE is_approved IS NULL"))

    # ── 3. Duplicate backfills before new UNIQUEs ────────────────────
    if _table_exists("shop_loyalty"):
        op.execute(
            sa.text("DELETE FROM shop_loyalty WHERE id NOT IN (SELECT MIN(id) FROM shop_loyalty GROUP BY account_id)")
        )
    if _table_exists("shop_stock_alerts"):
        op.execute(
            sa.text(
                "DELETE FROM shop_stock_alerts WHERE id NOT IN "
                "(SELECT MIN(id) FROM shop_stock_alerts GROUP BY tenant_id, email, product_id)"
            )
        )

    # ── 4. tenant_stores defaults + nullability ──────────────────────
    if _table_exists("tenant_stores"):
        with op.batch_alter_table("tenant_stores", schema=None) as batch_op:
            if _column_exists("tenant_stores", "is_enabled"):
                batch_op.alter_column(
                    "is_enabled",
                    existing_type=sa.Boolean(),
                    existing_nullable=False,
                    nullable=False,
                    server_default="false",
                )
            if _column_exists("tenant_stores", "low_stock_threshold"):
                batch_op.alter_column(
                    "low_stock_threshold",
                    existing_type=sa.Numeric(15, 3),
                    existing_nullable=True,
                    nullable=False,
                    server_default="5.000",
                )

    # ── 5. shop_reviews NOT NULL ─────────────────────────────────────
    if _table_exists("shop_reviews") and _column_exists("shop_reviews", "is_approved"):
        with op.batch_alter_table("shop_reviews", schema=None) as batch_op:
            batch_op.alter_column(
                "is_approved",
                existing_type=sa.Boolean(),
                existing_nullable=True,
                nullable=False,
                server_default="false",
            )

    # ── 6. Replace stock-alert unique scope ──────────────────────────
    _drop_unique("shop_stock_alerts", "uq_stock_alert_email_product")
    _add_unique("shop_stock_alerts", "uq_stock_alert_tenant_email_product", ["tenant_id", "email", "product_id"])

    # ── 7. New UNIQUEs ───────────────────────────────────────────────
    _add_unique("shop_loyalty", "uq_shop_loyalty_account", ["account_id"])

    # ── 8. CHECK constraints ─────────────────────────────────────────
    _add_check("shop_reviews", "ck_shop_review_rating_1_5", "rating BETWEEN 1 AND 5")
    _add_check(
        "store_coupons",
        "ck_store_coupon_pct_0_100",
        "discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)",
    )
    _add_check(
        "store_coupons",
        "ck_store_coupon_amt_nonneg",
        "discount_amount IS NULL OR discount_amount >= 0",
    )
    _add_check(
        "store_coupons",
        "ck_store_coupon_min_nonneg",
        "min_order_amount IS NULL OR min_order_amount >= 0",
    )

    # ── 9. Composite indexes ─────────────────────────────────────────
    _create_index("ix_tenant_stores_availability", "tenant_stores", ["is_enabled", "platform_disabled"])
    _create_index("ix_tenant_stores_is_enabled", "tenant_stores", ["is_enabled"])
    _create_index(
        "ix_shop_reviews_tenant_product_approved", "shop_reviews", ["tenant_id", "product_id", "is_approved"]
    )
    _create_index("ix_wishlist_tenant_account", "shop_wishlist", ["tenant_id", "account_id"])
    _create_index("ix_wishlist_tenant_product", "shop_wishlist", ["tenant_id", "product_id"])
    _create_index(
        "ix_saved_pay_tenant_account_method", "shop_saved_payments", ["tenant_id", "account_id", "method_code"]
    )
    _create_index("ix_variant_tenant_sku", "shop_product_variants", ["tenant_id", "sku"])
    _create_index("ix_variant_product_sort", "shop_product_variants", ["product_id", "sort_order"])
    _create_index("ix_stock_alerts_tenant_product", "shop_stock_alerts", ["tenant_id", "product_id"])
    _create_index("ix_stock_alerts_tenant_email", "shop_stock_alerts", ["tenant_id", "email"])
    _create_index("ix_abandoned_tenant_email", "shop_abandoned_carts", ["tenant_id", "email"])
    _create_index(
        "ix_abandoned_recovery_sweep", "shop_abandoned_carts", ["tenant_id", "recovered", "reminder_sent_at"]
    )
    _create_index(
        "ix_store_coupon_tenant_active_until", "store_coupons", ["tenant_id", "is_active", "valid_until"]
    )


def downgrade():
    for name, table in [
        ("ix_tenant_stores_availability", "tenant_stores"),
        ("ix_tenant_stores_is_enabled", "tenant_stores"),
        ("ix_shop_reviews_tenant_product_approved", "shop_reviews"),
        ("ix_wishlist_tenant_account", "shop_wishlist"),
        ("ix_wishlist_tenant_product", "shop_wishlist"),
        ("ix_saved_pay_tenant_account_method", "shop_saved_payments"),
        ("ix_variant_tenant_sku", "shop_product_variants"),
        ("ix_variant_product_sort", "shop_product_variants"),
        ("ix_stock_alerts_tenant_product", "shop_stock_alerts"),
        ("ix_stock_alerts_tenant_email", "shop_stock_alerts"),
        ("ix_abandoned_tenant_email", "shop_abandoned_carts"),
        ("ix_abandoned_recovery_sweep", "shop_abandoned_carts"),
        ("ix_store_coupon_tenant_active_until", "store_coupons"),
    ]:
        _drop_index(name, table)

    for table, name in [
        ("shop_reviews", "ck_shop_review_rating_1_5"),
        ("store_coupons", "ck_store_coupon_pct_0_100"),
        ("store_coupons", "ck_store_coupon_amt_nonneg"),
        ("store_coupons", "ck_store_coupon_min_nonneg"),
    ]:
        _drop_check(table, name)

    _drop_unique("shop_loyalty", "uq_shop_loyalty_account")
    _drop_unique("shop_stock_alerts", "uq_stock_alert_tenant_email_product")
    if _table_exists("shop_stock_alerts"):
        with op.batch_alter_table("shop_stock_alerts", schema=None) as batch_op:
            batch_op.create_unique_constraint("uq_stock_alert_email_product", ["email", "product_id"])

    if _table_exists("shop_reviews") and _column_exists("shop_reviews", "is_approved"):
        with op.batch_alter_table("shop_reviews", schema=None) as batch_op:
            batch_op.alter_column(
                "is_approved",
                existing_type=sa.Boolean(),
                existing_nullable=False,
                nullable=True,
            )

    if _table_exists("tenant_stores"):
        with op.batch_alter_table("tenant_stores", schema=None) as batch_op:
            if _column_exists("tenant_stores", "is_enabled"):
                batch_op.alter_column(
                    "is_enabled",
                    existing_type=sa.Boolean(),
                    existing_nullable=False,
                    nullable=False,
                )
            if _column_exists("tenant_stores", "low_stock_threshold"):
                batch_op.alter_column(
                    "low_stock_threshold",
                    existing_type=sa.Numeric(15, 3),
                    existing_nullable=False,
                    nullable=True,
                )

    if _table_exists("store_payment_methods") and _column_exists("store_payment_methods", "platform_disabled"):
        with op.batch_alter_table("store_payment_methods", schema=None) as batch_op:
            batch_op.drop_column("platform_disabled")
    if _table_exists("shop_abandoned_carts") and _column_exists("shop_abandoned_carts", "session_key"):
        with op.batch_alter_table("shop_abandoned_carts", schema=None) as batch_op:
            batch_op.drop_column("session_key")
