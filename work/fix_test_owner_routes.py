
with open(r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py', 'r') as f:
    content = f.read()

new_content = content.replace(
    '("routes.owner.render_template", patch("routes.owner.render_template", return_value="ok")),',
    '("routes.owner.render_template", patch("routes.owner.render_template", return_value="ok")),\n        ("flask.url_for", patch("flask.url_for", side_effect=lambda endpoint, **kwargs: "/")),'
)

with open(r'D:\Data\karaj\UAE\Azad-UAE\tests\unit\routes\test_owner_routes.py', 'w') as f:
    f.write(new_content)
