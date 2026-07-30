from extensions import db


class PosPrinter(db.Model):
    """Per-tenant POS printer definition with role-based ticket routing.

    ``role`` selects the job: ``customer`` receipts, ``kitchen`` tickets,
    ``warehouse`` pick slips. ``category_ids`` (JSON list) restricts a
    kitchen/warehouse printer to those product categories; empty means it
    receives every line. ``connection_type`` describes how the register
    reaches the printer: via the localhost hardware agent (network/serial)
    or directly from the browser (webusb/webserial).
    """

    __tablename__ = "pos_printers"

    ROLES = ("customer", "kitchen", "warehouse")
    CONNECTION_TYPES = ("agent_network", "agent_serial", "webusb", "webserial")

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id",ondelete="RESTRICT"), nullable=False, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey("branches.id",ondelete="RESTRICT"), nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    connection_type = db.Column(db.String(20), nullable=False, default="agent_network")
    host = db.Column(db.String(255), nullable=True)
    port = db.Column(db.Integer, nullable=True)
    serial_port = db.Column(db.String(40), nullable=True)
    baud_rate = db.Column(db.Integer, nullable=True)
    encoding = db.Column(db.String(20), nullable=False, default="cp864")
    category_ids = db.Column(db.JSON, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now())
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

    @property
    def categories(self):
        return list(self.category_ids or [])

    def covers_category(self, category_id):
        """Empty category list means the printer takes every line."""
        cats = self.categories
        if not cats:
            return True
        return category_id in cats

    def agent_printer_payload(self):
        """Printer block understood by the localhost hardware agent."""
        if self.connection_type == "agent_serial":
            return {"connection": "serial", "port": self.serial_port, "baud": self.baud_rate or 9600}
        return {
            "connection": "network",
            "host": self.host,
            "port": self.port or 9100,
            "encoding": self.encoding or "cp864",
        }

    @classmethod
    def for_tenant(cls, tenant_id, *, role=None, active_only=True):
        q = cls.query.filter_by(tenant_id=tenant_id)
        if active_only:
            q = q.filter_by(is_active=True)
        if role:
            q = q.filter_by(role=role)
        return q.order_by(cls.sort_order, cls.id).all()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "connection_type": self.connection_type,
            "host": self.host,
            "port": self.port,
            "serial_port": self.serial_port,
            "baud_rate": self.baud_rate,
            "encoding": self.encoding,
            "category_ids": self.categories,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
        }
