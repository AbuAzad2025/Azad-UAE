from datetime import datetime, timezone
from sqlalchemy import Index, text
from extensions import db


class ProductCategory(db.Model):
    __tablename__ = "product_categories"
    __table_args__ = (db.UniqueConstraint("tenant_id", "name", name="uq_product_categories_tenant_name"),)

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False, index=True)
    name_ar = db.Column(db.String(100))
    description = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey("product_categories.id"), index=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    parent = db.relationship("ProductCategory", remote_side=[id], backref="subcategories")
    products = db.relationship("Product", back_populates="category", lazy="dynamic")
    tenant = db.relationship("Tenant", backref="product_categories", foreign_keys=[tenant_id])

    def __repr__(self):
        return f"<Category {self.name}>"

    def get_display_name(self, lang="ar"):
        if lang == "ar" and self.name_ar:
            return self.name_ar
        return self.name


class ProductPartner(db.Model):
    __tablename__ = "product_partners"

    __table_args__ = (
        db.UniqueConstraint("product_id", "partner_customer_id", name="uq_product_partner"),
        db.Index("idx_product_partner_product", "product_id"),
        db.Index("idx_product_partner_partner", "partner_customer_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    partner_customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    percentage = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    product = db.relationship("Product", back_populates="partner_shares")
    partner_customer = db.relationship("Customer", foreign_keys=[partner_customer_id])
    tenant = db.relationship("Tenant", backref="product_partners", foreign_keys=[tenant_id])


class Product(db.Model):
    __tablename__ = "products"

    __table_args__ = (
        db.Index("idx_product_active_stock", "is_active", "current_stock"),
        db.Index("idx_product_category_active", "category_id", "is_active"),
        Index(
            "uq_products_tenant_sku",
            "tenant_id",
            "sku",
            unique=True,
            postgresql_where=text("(sku IS NOT NULL) AND (TRIM(sku::text) <> '')"),
        ),
        Index(
            "uq_products_tenant_barcode",
            "tenant_id",
            "barcode",
            unique=True,
            postgresql_where=text("(barcode IS NOT NULL) AND (TRIM(barcode::text) <> '')"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer,
        db.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(200), nullable=False, index=True)
    name_ar = db.Column(db.String(200))
    commercial_name = db.Column(db.String(200))

    sku = db.Column(db.String(50), index=True)
    part_number = db.Column(db.String(100), index=True)
    barcode = db.Column(db.String(100), index=True)

    country_of_origin = db.Column(db.String(100))

    category_id = db.Column(db.Integer, db.ForeignKey("product_categories.id"), index=True)
    category = db.relationship("ProductCategory", back_populates="products")
    tenant = db.relationship("Tenant", backref="products", foreign_keys=[tenant_id])

    merchant_customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), index=True)
    merchant_customer = db.relationship("Customer", foreign_keys=[merchant_customer_id])

    cost_price = db.Column(db.Numeric(15, 3), default=0)
    regular_price = db.Column(db.Numeric(15, 3), nullable=False)
    merchant_price = db.Column(db.Numeric(15, 3))
    merchant_share = db.Column(db.Numeric(5, 2), default=100.0)  # Percentage share for merchant owner
    partner_price = db.Column(db.Numeric(15, 3))

    current_stock = db.Column(db.Numeric(15, 3), default=0, nullable=False)
    min_stock_alert = db.Column(db.Numeric(15, 3), default=0)

    # Warranty & Serial Number Support
    has_serial_number = db.Column(db.Boolean, default=False, nullable=False)  # If true, each unit must have unique SN
    warranty_days = db.Column(db.Integer, default=0)  # Warranty duration in days (0 = No Warranty)

    # Alias for consistency (stock_quantity = current_stock)
    @property
    def stock_quantity(self):
        """Alias for current_stock for consistency"""
        return self.current_stock

    @stock_quantity.setter
    def stock_quantity(self, value):
        """Setter for stock_quantity"""
        self.current_stock = value

    # Another alias for quantity_in_stock
    @property
    def quantity_in_stock(self):
        """Alias for current_stock"""
        return self.current_stock

    @quantity_in_stock.setter
    def quantity_in_stock(self, value):
        """Setter for quantity_in_stock"""
        self.current_stock = value

    unit = db.Column(db.String(20), default="piece")
    location = db.Column(db.String(50))

    warranty_period = db.Column(db.Integer, default=0)
    warranty_unit = db.Column(db.String(20), default="months")

    is_returnable = db.Column(db.Boolean, default=True)
    return_period_days = db.Column(db.Integer, default=7)

    image_url = db.Column(db.String(255))
    description = db.Column(db.Text)
    notes = db.Column(db.Text)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    industry = db.Column(db.String(50), default="general")  # overrides tenant.business_type
    extra_fields = db.Column(db.JSON, default=dict)

    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    sale_lines = db.relationship("SaleLine", back_populates="product", lazy="dynamic")
    purchase_lines = db.relationship("PurchaseLine", back_populates="product", lazy="dynamic")
    stock_movements = db.relationship("StockMovement", back_populates="product", lazy="dynamic")
    partner_shares = db.relationship("ProductPartner", back_populates="product", cascade="all, delete-orphan")
    warehouse_stocks = db.relationship("ProductWarehouseStock", back_populates="product", lazy="dynamic")
    price_tiers = db.relationship("ProductPriceTier", back_populates="product", lazy="dynamic")
    images = db.relationship("ProductImage", back_populates="product", lazy="dynamic")

    def __repr__(self):
        return f"<Product {self.name}>"

    def get_price_for_customer(self, customer_type="regular"):
        if customer_type == "partner" and self.partner_price:
            # Treat partner_price as percentage discount
            return self.regular_price * (1 - (self.partner_price / 100))
        elif customer_type == "merchant" and self.merchant_price:
            # Treat merchant_price as percentage discount
            return self.regular_price * (1 - (self.merchant_price / 100))
        return self.regular_price

    def is_low_stock(self):
        if self.min_stock_alert is None:
            return False
        return self.current_stock <= self.min_stock_alert

    def is_out_of_stock(self):
        return self.current_stock <= 0

    def get_display_name(self, lang="ar"):
        if lang == "ar" and self.name_ar:
            return self.name_ar
        return self.name

    def get_cost(self):
        return self.cost_price

    def get_stock(self):
        return self.current_stock

    def to_dict(self, include_cost=False):
        data = {
            "id": self.id,
            "name": self.name,
            "name_ar": self.name_ar,
            "sku": self.sku,
            "barcode": self.barcode,
            "category": self.category.name if self.category else None,
            "regular_price": float(self.regular_price),
            "merchant_price": (float(self.merchant_price) if self.merchant_price else None),
            "partner_price": float(self.partner_price) if self.partner_price else None,
            "current_stock": float(self.current_stock),
            "unit": self.unit,
            "is_active": self.is_active,
            "is_low_stock": self.is_low_stock(),
        }

        if include_cost:
            data["cost_price"] = float(self.cost_price)

        return data
