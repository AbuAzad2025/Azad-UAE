from extensions import db


class IndustryFieldDefinition(db.Model):
    __tablename__ = "industry_field_definitions"

    id = db.Column(db.Integer, primary_key=True)
    industry_code = db.Column(db.String(50), nullable=False, index=True)
    field_code = db.Column(db.String(50), nullable=False)
    field_name_ar = db.Column(db.String(100), nullable=False)
    field_name_en = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(20), default="text")
    field_options = db.Column(db.JSON, default=list)
    applies_to = db.Column(db.String(20), default="product")
    sort_order = db.Column(db.Integer, default=0)
    is_required = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True, index=True)

    __table_args__ = (db.UniqueConstraint("industry_code", "field_code", name="uq_industry_field_code"),)

    def __repr__(self):
        return f"<IndustryField {self.industry_code}.{self.field_code}>"
