from datetime import datetime, timezone
from extensions import db

class ProductSerial(db.Model):
    __tablename__ = 'product_serials'
    
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    
    serial_number = db.Column(db.String(100), nullable=False, unique=True, index=True)
    
    # Lifecycle Status
    status = db.Column(db.String(20), default='available', index=True) 
    # available: In stock, ready to sell
    # sold: Sold to customer
    # returned: Returned by customer (faulty/good)
    # defective: Marked as bad/damaged
    # lost: Lost/Stolen
    
    # Tracking
    purchase_line_id = db.Column(db.Integer, db.ForeignKey('purchase_lines.id'), nullable=True) # Where did we get it?
    sale_line_id = db.Column(db.Integer, db.ForeignKey('sale_lines.id'), nullable=True) # Who did we sell it to?
    
    # Warranty Info (Calculated from Sale Date)
    warranty_start_date = db.Column(db.DateTime, nullable=True)
    warranty_end_date = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    product = db.relationship('Product', backref='serials')
    purchase_line = db.relationship('PurchaseLine', backref='serials')
    sale_line = db.relationship('SaleLine', backref='serials')
    
    def __repr__(self):
        return f'<Serial {self.serial_number} ({self.status})>'
