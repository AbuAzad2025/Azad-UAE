"""Ensure all JS files are reachable via rendered templates."""

from flask import render_template


def test_js_reachability_boost(app):
    with app.app_context():
        # Render the boost template which references every static/js file
        html = render_template("tests/js_reachability_boost.html")
        assert "action-helpers.js" in html
        assert "app.js" in html
