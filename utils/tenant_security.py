"""
Tenant Security Decorators — Route-level tenant ownership validation.

Provides decorators to ensure that resources accessed via API endpoints belong
to the current tenant, preventing cross-tenant data access at the application layer.
"""

from functools import wraps
from flask import abort, g
from flask_login import current_user
from extensions import db


def validate_tenant_ownership(model_class):
    """
    Decorator to validate that a resource belongs to the current tenant.

    This decorator automatically inspects the route function signature to find
    the first parameter that matches the model name (e.g., 'product_id' for Product),
    queries the record, and verifies that it belongs to g.active_tenant_id.
    If the record does not exist or belongs to a different tenant, it raises
    a 404 Not Found exception.

    Args:
        model_class: The SQLAlchemy model class to query

    Usage:
        @bp.route('/products/<int:product_id>')
        @validate_tenant_ownership(Product)
        def get_product(product_id):
            # At this point, product_id is guaranteed to belong to current tenant
            product = db.session.get(Product, product_id)
            return jsonify(product.to_dict())

    Security:
        - Prevents cross-tenant data access at the application layer
        - Works in conjunction with ORM-level tenant scoping
        - Provides defense-in-depth against tenant isolation bypasses
        - Always returns 404 for cross-tenant attempts (doesn't leak existence)
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Auto-detect resource ID parameter from function signature
            import inspect

            sig = inspect.signature(f)
            param_names = list(sig.parameters.keys())

            # Find the ID parameter (e.g., 'product_id', 'customer_id')
            resource_id = None
            for param_name in param_names:
                if param_name.endswith("_id") or param_name == "id":
                    resource_id = kwargs.get(param_name)
                    if resource_id is not None:
                        break

            if resource_id is None:
                # Fallback: try first parameter if no _id suffix found
                if param_names:
                    resource_id = kwargs.get(param_names[0])

            if resource_id is None:
                abort(400, description="Missing required resource ID parameter")

            # Get current tenant ID from global context
            tenant_id = getattr(g, "active_tenant_id", None)
            if tenant_id is None:
                # If no tenant context, deny access (unless platform owner with explicit tenant selection)
                from utils.tenanting import is_platform_owner

                if not is_platform_owner(current_user):
                    abort(404, description="Resource not found")

            # Query the resource
            resource = db.session.get(model_class, int(resource_id or 0))
            if resource is None:
                abort(404, description=f"{model_class.__name__} not found")

            # Validate tenant ownership
            resource_tenant_id = getattr(resource, "tenant_id", None)
            if resource_tenant_id is None:
                # Resources without tenant_id can only be accessed by platform owners
                from utils.tenanting import is_platform_owner

                if not is_platform_owner(current_user):
                    abort(404, description="Resource not found")
            else:
                # For tenant-scoped resources, strict ownership check
                if tenant_id is not None and int(resource_tenant_id or 0) != int(tenant_id or 0):
                    abort(404, description=f"{model_class.__name__} not found")  # Return 404 to avoid leaking existence

            # Resource belongs to current tenant, proceed with the route
            return f(*args, **kwargs)

        return wrapped

    return decorator


def require_tenant_context(f):
    """
    Decorator to ensure an active tenant context exists for the request.

    Use this on routes that require tenant context but don't access specific
    resources by ID (e.g., list endpoints, create endpoints).

    Usage:
        @bp.route('/products')
        @require_tenant_context
        def list_products():
            products = Product.query.filter_by(tenant_id=g.active_tenant_id).all()
            return jsonify([p.to_dict() for p in products])
    """

    @wraps(f)
    def wrapped(*args, **kwargs):
        tenant_id = getattr(g, "active_tenant_id", None)
        if tenant_id is None:
            from utils.tenanting import is_platform_owner

            if not is_platform_owner(current_user):
                abort(403, description="Active tenant context required")
        return f(*args, **kwargs)

    return wrapped
