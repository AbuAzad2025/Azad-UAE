import os

import re



from flask import Blueprint, request, jsonify, abort, current_app

from flask_login import login_required, current_user

from extensions import limiter

from services.graphql_service import build_schema



graphql_bp = Blueprint('graphql', __name__, url_prefix='/graphql')



_MAX_QUERY_LENGTH = 8000

_MAX_QUERY_DEPTH = 8

_INTROSPECTION_RE = re.compile(r'__schema\b|__type\s*\(', re.IGNORECASE)





def _mutations_allowed():

    app_env = (os.environ.get('APP_ENV') or 'production').strip().lower()

    debug = (os.environ.get('DEBUG') or '').strip().lower() in ('1', 'true', 'yes', 'y')

    return debug or app_env != 'production'





def _is_production_env() -> bool:

    app_env = (os.environ.get('APP_ENV') or 'production').strip().lower()

    debug = (os.environ.get('DEBUG') or '').strip().lower() in ('1', 'true', 'yes', 'y')

    return app_env == 'production' and not debug





def _query_depth(query: str) -> int:

    depth = 0

    max_depth = 0

    for char in query:

        if char == '{':

            depth += 1

            max_depth = max(max_depth, depth)

        elif char == '}':

            depth = max(0, depth - 1)

    return max_depth





def _is_introspection_query(query: str) -> bool:

    normalized = ' '.join(query.split())

    return bool(_INTROSPECTION_RE.search(normalized))





@graphql_bp.route('', methods=['POST'])

@login_required

@limiter.limit("60 per minute")

def graphql_query():

    data = request.get_json(silent=True) or {}

    query = (data.get('query') or '').strip()

    variables = data.get('variables')



    if not query:

        return jsonify({'errors': ['Query is required']}), 400



    if len(query) > _MAX_QUERY_LENGTH:

        return jsonify({'errors': ['Query too long']}), 413



    if _query_depth(query) > _MAX_QUERY_DEPTH:

        return jsonify({'errors': ['Query exceeds maximum depth']}), 400



    if _is_production_env() and _is_introspection_query(query):

        current_app.logger.warning(

            'GraphQL introspection blocked user_id=%s',

            getattr(current_user, 'id', None),

        )

        return jsonify({'errors': ['Introspection is disabled in production']}), 403



    if not _mutations_allowed() and 'mutation' in query.lower():

        return jsonify({'errors': ['GraphQL mutations are disabled in this environment']}), 403



    schema = build_schema(allow_mutations=_mutations_allowed())

    result = schema.execute(query, variables=variables)

    

    response = {}

    if result.data:

        response['data'] = result.data

    if result.errors:

        response['errors'] = [str(e) for e in result.errors]

    

    return jsonify(response)





@graphql_bp.route('/playground', methods=['GET'])

@login_required

def graphql_playground():

    if not _mutations_allowed():

        abort(404)

    if not getattr(current_user, 'is_owner', False):

        abort(403)

    return '''

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

    '''

