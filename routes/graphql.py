from flask import Blueprint, request, jsonify
from flask_login import login_required
from services.graphql_service import schema

graphql_bp = Blueprint('graphql', __name__, url_prefix='/graphql')


@graphql_bp.route('', methods=['POST'])
@login_required
def graphql_query():
    data = request.get_json()
    query = data.get('query')
    variables = data.get('variables')
    
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

