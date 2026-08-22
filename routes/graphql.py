import os
import re

from flask import Blueprint, abort, current_app, request
from flask_login import current_user, login_required

from extensions import limiter
from services.graphql_service import build_schema
from utils.api_response import error_response, success_response

graphql_bp = Blueprint("graphql", __name__, url_prefix="/graphql")


_MAX_QUERY_LENGTH = 8000

_MAX_QUERY_DEPTH = 8

_INTROSPECTION_RE = re.compile(r"__schema\b|__type\s*\(", re.IGNORECASE)


def _mutations_allowed():

    app_env = (os.environ.get("APP_ENV") or "production").strip().lower()

    debug = (os.environ.get("DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")

    return debug or app_env != "production"


def _is_production_env() -> bool:

    app_env = (os.environ.get("APP_ENV") or "production").strip().lower()

    debug = (os.environ.get("DEBUG") or "").strip().lower() in ("1", "true", "yes", "y")

    return app_env == "production" and not debug


def _query_depth(query: str) -> int:

    depth = 0

    max_depth = 0

    for char in query:
        if char == "{":
            depth += 1

            max_depth = max(max_depth, depth)

        elif char == "}":
            depth = max(0, depth - 1)

    return max_depth


def _is_introspection_query(query: str) -> bool:

    normalized = " ".join(query.split())

    return bool(_INTROSPECTION_RE.search(normalized))


@graphql_bp.route("", methods=["POST"])
@login_required
@limiter.limit("60 per minute")
def graphql_query():

    data = request.get_json(silent=True) or {}

    query = (data.get("query") or "").strip()

    variables = data.get("variables")

    if not query:
        return error_response(message="Query is required", errors=["Query is required"], status_code=400)

    if len(query) > _MAX_QUERY_LENGTH:
        return error_response(message="Query too long", errors=["Query too long"], status_code=413)

    if _query_depth(query) > _MAX_QUERY_DEPTH:
        return error_response(
            message="Query exceeds maximum depth",
            errors=["Query exceeds maximum depth"],
            status_code=400,
        )

    if _is_production_env() and _is_introspection_query(query):
        current_app.logger.warning(
            "GraphQL introspection blocked user_id=%s",
            getattr(current_user, "id", None),
        )

        return error_response(
            message="Introspection is disabled in production",
            errors=["Introspection is disabled in production"],
            status_code=403,
        )

    if not _mutations_allowed() and "mutation" in query.lower():
        return error_response(
            message="GraphQL mutations are disabled in this environment",
            errors=["GraphQL mutations are disabled in this environment"],
            status_code=403,
        )

    schema = build_schema(allow_mutations=_mutations_allowed())

    result = schema.execute(query, variables=variables)

    response = {}

    if result.data:
        response["data"] = result.data

    if result.errors:
        response["errors"] = [str(e) for e in result.errors]

    return success_response(data=response)


@graphql_bp.route("/playground", methods=["GET"])
@login_required
def graphql_playground():

    if not _mutations_allowed():
        abort(404)

    if not getattr(current_user, "is_owner", False):
        abort(403)

    return """

    <!DOCTYPE html>

    <html>

    <head>

        <title>GraphQL Playground</title>

        <meta charset="utf-8">

        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/graphql-playground-react/build/static/css/index.css" />

    </head>

    <body>

        <div id="root"></div>

        <script src="https://cdn.jsdelivr.net/npm/graphql-playground-react/build/static/js/middleware.js"></script>

        <script>

            window.addEventListener('load', function (event) {

                GraphQLPlayground.init(document.getElementById('root'), {

                    endpoint: '/graphql'

                })

            })

        </script>

    </body>

    </html>

    """
