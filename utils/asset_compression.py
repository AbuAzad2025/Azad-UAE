"""
Asset Compression and Minification Utilities
"""
import os
import gzip
import hashlib
from pathlib import Path

import click
from flask import current_app


class AssetCompressor:
    """Compress and minify CSS/JS assets for production"""
    
    STATIC_DIR = 'static'
    CSS_DIR = 'css'
    JS_DIR = 'js'
    
    @staticmethod
    def minify_css(content):
        """Minify CSS content"""
        import re

        content = re.sub(r'/\*[^*]*\*+(?:[^/*][^*]*\*+)*/', '', content)
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\s*([{}:;,>+~])\s*', r'\1', content)
        content = re.sub(r';}', '}', content)

        return content.strip()
    
    @staticmethod
    def minify_js(content):
        """Minify JavaScript content (basic)"""
        import re

        content = re.sub(r'//.*?\n', '\n', content)
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        content = re.sub(r'\s+', ' ', content)
        content = re.sub(r'\s*([{}();,:])\s*', r'\1', content)

        return content.strip()
    
    @staticmethod
    def gzip_file(file_path):
        gz_path = f"{file_path}.gz"
        
        with open(file_path, 'rb') as f_in:
            with gzip.open(gz_path, 'wb', compresslevel=9) as f_out:
                f_out.writelines(f_in)
        
        return gz_path
    
    @staticmethod
    def get_file_hash(content):
        return hashlib.sha256(content.encode(), usedforsecurity=False).hexdigest()[:8]
    
    @classmethod
    def process_css_files(cls, base_dir='static/css'):
        """Process all CSS files"""
        results = []
        css_dir = Path(base_dir)
        
        if not css_dir.exists():
            return results
        
        for css_file in css_dir.glob('**/*.css'):
            if css_file.name.endswith('.min.css'):
                continue
            
            try:
                with open(css_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                minified = cls.minify_css(content)

                min_path = css_file.parent / f"{css_file.stem}.min.css"
                with open(min_path, 'w', encoding='utf-8') as f:
                    f.write(minified)

                gz_path = cls.gzip_file(str(min_path))
                
                original_size = len(content)
                minified_size = len(minified)
                gz_size = os.path.getsize(gz_path)
                
                results.append({
                    'file': str(css_file.name),
                    'original': original_size,
                    'minified': minified_size,
                    'gzipped': gz_size,
                    'savings': round((1 - gz_size/original_size) * 100, 2)
                })

                click.echo(f"✅ {css_file.name}: {original_size} → {minified_size} → {gz_size} bytes ({results[-1]['savings']}% saved)")

            except Exception as e:
                click.echo(f"❌ Error processing {css_file}: {e}")
        
        return results
    
    @classmethod
    def process_js_files(cls, base_dir='static/js'):
        """Process all JS files"""
        results = []
        js_dir = Path(base_dir)
        
        if not js_dir.exists():
            return results
        
        for js_file in js_dir.glob('**/*.js'):
            if js_file.name.endswith('.min.js'):
                continue
            
            try:
                with open(js_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                minified = cls.minify_js(content)

                min_path = js_file.parent / f"{js_file.stem}.min.js"
                with open(min_path, 'w', encoding='utf-8') as f:
                    f.write(minified)

                gz_path = cls.gzip_file(str(min_path))
                
                original_size = len(content)
                minified_size = len(minified)
                gz_size = os.path.getsize(gz_path)
                
                results.append({
                    'file': str(js_file.name),
                    'original': original_size,
                    'minified': minified_size,
                    'gzipped': gz_size,
                    'savings': round((1 - gz_size/original_size) * 100, 2)
                })

                click.echo(f"✅ {js_file.name}: {original_size} → {minified_size} → {gz_size} bytes ({results[-1]['savings']}% saved)")

            except Exception as e:
                click.echo(f"❌ Error processing {js_file}: {e}")
        
        return results
    
    @classmethod
    def compress_all(cls):
        """Compress all assets"""
        click.echo("🔧 Starting asset compression...")
        
        css_results = cls.process_css_files()
        js_results = cls.process_js_files()
        
        total_original = sum(r['original'] for r in css_results + js_results)
        total_compressed = sum(r['gzipped'] for r in css_results + js_results)
        
        click.echo("\n" + "="*60)
        click.echo("📊 Compression Summary")
        click.echo("="*60)
        click.echo(f"CSS Files: {len(css_results)}")
        click.echo(f"JS Files: {len(js_results)}")
        click.echo(f"Total Original: {total_original:,} bytes")
        click.echo(f"Total Compressed: {total_compressed:,} bytes")
        total_savings = 0.0 if total_original == 0 else round((1 - total_compressed / total_original) * 100, 2)
        click.echo(f"Total Savings: {total_savings}%")
        click.echo("="*60)
        
        return {
            'css': css_results,
            'js': js_results,
            'total_savings': total_savings,
        }


def register_compression_cli(app):
    """Register CLI commands for asset compression"""
    
    @app.cli.command('compress-assets')
    def compress_assets():
        """Compress CSS and JS assets"""
        results = AssetCompressor.compress_all()
        click.echo("\n✅ Asset compression completed!")
        click.echo(f"📦 Total savings: {results['total_savings']}%")

