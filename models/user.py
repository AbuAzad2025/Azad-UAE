# models/user.py
# User, Role, and Permission models

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from extensions import db

# Association table for Role-Permission many-to-many
role_permissions = db.Table(
    'role_permissions',
    db.Column('role_id', db.Integer, db.ForeignKey('roles.id'), primary_key=True),
    db.Column('permission_id', db.Integer, db.ForeignKey('permissions.id'), primary_key=True)
)


class Permission(db.Model):
    """Permission model - defines what actions users can perform"""
    __tablename__ = 'permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g., 'manage_sales'
    name = db.Column(db.String(100), nullable=False)  # Display name
    name_ar = db.Column(db.String(100))  # Arabic name
    description = db.Column(db.String(255))
    category = db.Column(db.String(50))  # Group permissions: 'sales', 'products', 'reports', etc.
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    def __repr__(self):
        return f'<Permission {self.code}>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'name_ar': self.name_ar,
            'category': self.category,
        }


class Role(db.Model):
    """Role model - defines user roles with permissions"""
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # Display name
    name_ar = db.Column(db.String(50))  # Arabic name
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)  # e.g., 'super_admin'
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    permissions = db.relationship('Permission', secondary=role_permissions, backref='roles', lazy='joined')
    users = db.relationship('User', back_populates='role', lazy='dynamic')
    
    def __repr__(self):
        return f'<Role {self.name}>'
    
    def has_permission(self, permission_code):
        """Check if role has a specific permission"""
        return any(p.code == permission_code for p in self.permissions)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'name_ar': self.name_ar,
            'slug': self.slug,
            'permissions': [p.code for p in self.permissions],
        }


class User(UserMixin, db.Model):
    """User model - system users (Super Admin, Manager, Seller)"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile
    full_name = db.Column(db.String(100))
    full_name_ar = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    
    # Role
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, index=True)
    role = db.relationship('Role', back_populates='users')
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True, index=True) # User Home Branch
    branch = db.relationship('Branch', backref='users', foreign_keys=[branch_id])
    tenant = db.relationship('Tenant', backref='users', foreign_keys=[tenant_id])
    
    is_owner = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    email_verified = db.Column(db.Boolean, default=False)
    
    # Login tracking
    last_login = db.Column(db.DateTime)
    last_seen = db.Column(db.DateTime)
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    sales = db.relationship('Sale', back_populates='seller', lazy='dynamic', foreign_keys='Sale.seller_id')
    audit_logs = db.relationship('AuditLog', back_populates='user', lazy='dynamic')
    
    # Avoid circular imports - use strings for forward references
    # created_suppliers = db.relationship('Supplier', foreign_keys='Supplier.created_by', lazy='dynamic')
    # created_tenants = db.relationship('Tenant', foreign_keys='Tenant.created_by', lazy='dynamic')
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def is_super_admin(self):
        return self.role and self.role.slug == 'super_admin'
    
    def is_admin(self):
        """Admin = Owner OR Super Admin"""
        return self.is_owner or self.is_super_admin()
    
    def is_manager(self):
        return self.role and self.role.slug == 'manager'
    
    def is_seller(self):
        return self.role and self.role.slug == 'seller'
    
    def has_permission(self, permission_code):
        if self.is_owner:
            return True
        return self.role and self.role.has_permission(permission_code)
    
    def can_see_costs(self):
        return self.is_owner or self.is_super_admin() or self.is_manager()

    def can_apply_discount(self):
        """Cashiers cannot apply discounts without supervisor override."""
        if self.is_owner:
            return True
        return self.role and self.role.slug not in ('seller', 'cashier')

    def can_edit_price(self):
        """Cashiers cannot edit prices without supervisor override."""
        if self.is_owner:
            return True
        return self.role and self.role.slug not in ('seller', 'cashier')
    
    def get_display_name(self, lang='ar'):
        """Get display name in specified language"""
        if lang == 'ar' and self.full_name_ar:
            return self.full_name_ar
        return self.full_name or self.username
    
    def to_dict(self, include_sensitive=False):
        data = {
            'id': self.id,
            'username': self.username if not self.is_owner else '***',
            'email': self.email if not self.is_owner else '***@***.***',
            'full_name': self.full_name,
            'full_name_ar': self.full_name_ar,
            'phone': self.phone,
            'role': self.role.to_dict() if self.role else None,
            'is_active': self.is_active,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'created_at': self.created_at.isoformat(),
        }
        
        if include_sensitive and not self.is_owner:
            data.update({
                'email_verified': self.email_verified,
                'login_attempts': self.login_attempts,
                'locked_until': self.locked_until.isoformat() if self.locked_until else None,
                'last_login': self.last_login.isoformat() if self.last_login else None,
            })
        
        return data

