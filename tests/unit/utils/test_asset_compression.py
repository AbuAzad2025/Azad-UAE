from __future__ import annotations

import gzip
from pathlib import Path
from unittest.mock import MagicMock

from utils.asset_compression import AssetCompressor, register_compression_cli


class TestMinifyCss:
    def test_strips_comments_and_whitespace(self):
        raw = "/* header */\n.foo { color: red; }\n.bar { margin: 0; }"
        result = AssetCompressor.minify_css(raw)
        assert '/*' not in result
        assert '.foo' in result
        assert 'color' in result
        assert 'red' in result

    def test_empty_input(self):
        assert AssetCompressor.minify_css('') == ''


class TestMinifyJs:
    def test_strips_line_comments(self):
        raw = "var x = 1;\n// comment\nvar y = 2;"
        result = AssetCompressor.minify_js(raw)
        assert 'comment' not in result
        assert 'var' in result
        assert 'x' in result

    def test_block_comments(self):
        raw = "/* block */ function foo() { return 1; }"
        result = AssetCompressor.minify_js(raw)
        assert 'block' not in result


class TestGzipFile:
    def test_creates_gz_sibling(self, tmp_path):
        src = tmp_path / 'app.css'
        src.write_text('.x{color:red}', encoding='utf-8')
        gz_path = AssetCompressor.gzip_file(str(src))
        assert Path(gz_path).exists()
        with gzip.open(gz_path, 'rb') as f:
            assert b'.x{color:red}' in f.read()


class TestGetFileHash:
    def test_returns_eight_char_hex(self):
        h = AssetCompressor.get_file_hash('hello world')
        assert len(h) == 8
        assert h == AssetCompressor.get_file_hash('hello world')


class TestProcessCssFiles:
    def test_missing_dir_returns_empty(self, tmp_path):
        assert AssetCompressor.process_css_files(str(tmp_path / 'missing')) == []

    def test_skips_already_minified(self, tmp_path):
        css_dir = tmp_path / 'css'
        css_dir.mkdir()
        (css_dir / 'app.min.css').write_text('.x{}', encoding='utf-8')
        assert AssetCompressor.process_css_files(str(css_dir)) == []

    def test_processes_css_file(self, tmp_path, mocker):
        css_dir = tmp_path / 'css'
        css_dir.mkdir()
        css_file = css_dir / 'app.css'
        css_file.write_text('.foo { color: blue; }', encoding='utf-8')
        mocker.patch('utils.asset_compression.click.echo')
        results = AssetCompressor.process_css_files(str(css_dir))
        assert len(results) == 1
        assert results[0]['file'] == 'app.css'
        assert (css_dir / 'app.min.css').exists()
        assert (css_dir / 'app.min.css.gz').exists()

    def test_handles_read_error(self, tmp_path, mocker):
        css_dir = tmp_path / 'css'
        css_dir.mkdir()
        css_file = css_dir / 'bad.css'
        css_file.write_text('x', encoding='utf-8')
        mocker.patch('utils.asset_compression.click.echo')
        mocker.patch('builtins.open', side_effect=OSError('read fail'))
        results = AssetCompressor.process_css_files(str(css_dir))
        assert results == []


class TestProcessJsFiles:
    def test_missing_dir_returns_empty(self, tmp_path):
        assert AssetCompressor.process_js_files(str(tmp_path / 'missing')) == []

    def test_processes_js_file(self, tmp_path, mocker):
        js_dir = tmp_path / 'js'
        js_dir.mkdir()
        (js_dir / 'app.js').write_text('var a = 1;', encoding='utf-8')
        mocker.patch('utils.asset_compression.click.echo')
        results = AssetCompressor.process_js_files(str(js_dir))
        assert len(results) == 1
        assert (js_dir / 'app.min.js').exists()


class TestCompressAll:
    def test_empty_dirs_zero_savings(self, tmp_path, mocker):
        mocker.patch('utils.asset_compression.click.echo')
        mocker.patch.object(AssetCompressor, 'process_css_files', return_value=[])
        mocker.patch.object(AssetCompressor, 'process_js_files', return_value=[])
        result = AssetCompressor.compress_all()
        assert result['total_savings'] == 0.0

    def test_aggregates_results(self, mocker):
        mocker.patch('utils.asset_compression.click.echo')
        css = [{'file': 'a.css', 'original': 100, 'minified': 80, 'gzipped': 40, 'savings': 60.0}]
        js = [{'file': 'b.js', 'original': 200, 'minified': 150, 'gzipped': 100, 'savings': 50.0}]
        mocker.patch.object(AssetCompressor, 'process_css_files', return_value=css)
        mocker.patch.object(AssetCompressor, 'process_js_files', return_value=js)
        result = AssetCompressor.compress_all()
        assert result['css'] == css
        assert result['js'] == js
        assert result['total_savings'] == 53.33


class TestRegisterCompressionCli:
    def test_registers_cli_command(self):
        app = MagicMock()
        register_compression_cli(app)
        app.cli.command.assert_called_once_with('compress-assets')

    def test_cli_handler_runs(self, mocker):
        app = MagicMock()
        register_compression_cli(app)
        _handler = app.cli.command.call_args[1].get('f') or app.cli.command.return_value
        mocker.patch('utils.asset_compression.AssetCompressor.compress_all', return_value={'total_savings': 10.0})
        mocker.patch('utils.asset_compression.click.echo')
        from click.testing import CliRunner
        from flask import Flask
        real_app = Flask(__name__)
        register_compression_cli(real_app)
        runner = CliRunner()
        result = runner.invoke(real_app.cli, ['compress-assets'])
        assert result.exit_code == 0


class TestProcessJsCoverageGaps:
    def test_skips_already_minified(self, tmp_path):
        js_dir = tmp_path / 'js'
        js_dir.mkdir()
        (js_dir / 'app.min.js').write_text('var x=1;', encoding='utf-8')
        assert AssetCompressor.process_js_files(str(js_dir)) == []

    def test_handles_read_error(self, tmp_path, mocker):
        js_dir = tmp_path / 'js'
        js_dir.mkdir()
        (js_dir / 'bad.js').write_text('x', encoding='utf-8')
        mocker.patch('utils.asset_compression.click.echo')
        mocker.patch('builtins.open', side_effect=OSError('read fail'))
        assert AssetCompressor.process_js_files(str(js_dir)) == []

