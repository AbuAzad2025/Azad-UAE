def register_build_assets_command(app):
    @app.cli.command('build-assets')
    def build_assets():
        """Minify, hash, and compress static assets."""
        from scripts.build_assets import build_all
        build_all()

def register_cli_commands(app):
    register_build_assets_command(app)
