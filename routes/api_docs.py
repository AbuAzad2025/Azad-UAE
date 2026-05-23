"""
API Documentation using OpenAPI/Swagger
"""
from flask import Blueprint, jsonify, render_template_string, current_app
import copy

api_docs_bp = Blueprint('api_docs', __name__, url_prefix='/api-docs')


# OpenAPI 3.0 Specification
OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "Garage Management System API",
        "description": "RESTful API for managing garage operations, sales, inventory, and accounting",
        "version": "2.0.0",
        "contact": {
            "name": "Azad Smart Systems",
            "email": "dev@example.com",
            "url": "https://azadsystems.com"
        },
        "license": {
            "name": "Proprietary",
            "url": "https://azadsystems.com/license"
        }
    },
    "servers": [
        {
            "url": "http://localhost:5000/api",
            "description": "Development server"
        },
        {
            "url": "https://api.yourdomain.com/api",
            "description": "Production server"
        }
    ],
    "tags": [
        {"name": "Auth", "description": "Authentication endpoints"},
        {"name": "Customers", "description": "Customer management"},
        {"name": "Suppliers", "description": "Supplier management"},
        {"name": "Products", "description": "Product catalog"},
        {"name": "Sales", "description": "Sales operations"},
        {"name": "Purchases", "description": "Purchase operations"},
        {"name": "Payments", "description": "Payment processing"},
        {"name": "Reports", "description": "Reporting and analytics"},
        {"name": "Search", "description": "Universal search"}
    ],
    "paths": {
        "/search": {
            "get": {
                "tags": ["Search"],
                "summary": "Universal search across entities",
                "description": "Search for customers, suppliers, or products",
                "parameters": [
                    {
                        "name": "type",
                        "in": "query",
                        "required": True,
                        "schema": {
                            "type": "string",
                            "enum": ["customers", "suppliers", "products"]
                        },
                        "description": "Type of entity to search"
                    },
                    {
                        "name": "q",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "Search query"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Search results",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "results": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "id": {"type": "integer"},
                                                    "text": {"type": "string"},
                                                    "info": {"type": "string"}
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "/customer-balance/{id}": {
            "get": {
                "tags": ["Customers"],
                "summary": "Get customer balance",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"},
                        "description": "Customer ID"
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Customer balance information",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "customer_id": {"type": "integer"},
                                        "name": {"type": "string"},
                                        "balance": {"type": "number"},
                                        "currency": {"type": "string"}
                                    }
                                }
                            }
                        }
                    },
                    "404": {
                        "description": "Customer not found"
                    }
                }
            }
        }
    },
    "components": {
        "securitySchemes": {
            "sessionAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "session"
            }
        },
        "schemas": {
            "Customer": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "name_ar": {"type": "string"},
                    "customer_type": {
                        "type": "string",
                        "enum": ["regular", "merchant", "partner"]
                    },
                    "phone": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "balance": {"type": "number"},
                    "is_active": {"type": "boolean"}
                }
            },
            "Product": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "name_ar": {"type": "string"},
                    "barcode": {"type": "string"},
                    "regular_price": {"type": "number"},
                    "merchant_price": {"type": "number"},
                    "partner_price": {"type": "number"},
                    "cost_price": {"type": "number"},
                    "quantity_in_stock": {"type": "integer"},
                    "is_active": {"type": "boolean"}
                }
            },
            "Sale": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "invoice_number": {"type": "string"},
                    "customer_id": {"type": "integer"},
                    "sale_date": {"type": "string", "format": "date-time"},
                    "total_amount": {"type": "number"},
                    "amount_paid": {"type": "number"},
                    "remaining_balance": {"type": "number"},
                    "payment_status": {
                        "type": "string",
                        "enum": ["paid", "partial", "credit"]
                    },
                    "currency": {"type": "string"}
                }
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"},
                    "message": {"type": "string"}
                }
            }
        }
    },
    "security": [
        {"sessionAuth": []}
    ]
}


@api_docs_bp.route('/openapi.json')
def openapi_spec():
    """Return OpenAPI specification as JSON"""
    spec = copy.deepcopy(OPENAPI_SPEC)
    spec["info"]["contact"]["name"] = current_app.config.get("DEVELOPER_NAME", spec["info"]["contact"].get("name"))
    spec["info"]["contact"]["email"] = current_app.config.get("DEVELOPER_EMAIL", spec["info"]["contact"].get("email"))
    spec["info"]["contact"]["url"] = current_app.config.get("DEVELOPER_WEBSITE", spec["info"]["contact"].get("url"))
    return jsonify(spec)


@api_docs_bp.route('/')
def swagger_ui():
    """Swagger UI for API documentation"""
    html = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>API Documentation - Garage Management System</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
        <style>
            body { margin: 0; padding: 0; }
            .topbar { display: none; }
        </style>
    </head>
    <body>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>
        <script>
            window.onload = function() {
                SwaggerUIBundle({
                    url: '/api-docs/openapi.json',
                    dom_id: '#swagger-ui',
                    deepLinking: true,
                    presets: [
                        SwaggerUIBundle.presets.apis,
                        SwaggerUIStandalonePreset
                    ],
                    layout: "BaseLayout",
                    supportedSubmitMethods: ['get', 'post', 'put', 'delete', 'patch'],
                    defaultModelsExpandDepth: 1,
                    defaultModelExpandDepth: 1,
                    displayOperationId: false,
                    showExtensions: false,
                    showCommonExtensions: false,
                    tryItOutEnabled: true
                });
            };
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


@api_docs_bp.route('/redoc')
def redoc():
    """ReDoc alternative documentation"""
    html = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>API Documentation - Garage Management System</title>
        <style>
            body { margin: 0; padding: 0; }
        </style>
    </head>
    <body>
        <redoc spec-url='/api-docs/openapi.json'></redoc>
        <script src="https://cdn.jsdelivr.net/npm/redoc@latest/bundles/redoc.standalone.js"></script>
    </body>
    </html>
    """
    return render_template_string(html)

