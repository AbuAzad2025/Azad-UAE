from pathlib import Path
import hashlib

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestStaticFilesAudit:
    def _get_static_files(self, ext=None):
        static_dir = PROJECT_ROOT / 'static'
        if not static_dir.exists():
            return []
        if ext:
            return [p for p in static_dir.rglob(f'*.{ext}') if p.is_file()]
        return [p for p in static_dir.rglob('*') if p.is_file()]

    def test_static_directory_exists(self):
        static_dir = PROJECT_ROOT / 'static'
        assert static_dir.exists(), 'static directory does not exist'
        assert static_dir.is_dir(), 'static is not a directory'

    def test_js_files_source_and_min_pairs(self):
        static_dir = PROJECT_ROOT / 'static'
        js_files = list(static_dir.rglob('*.js'))
        min_files = [p for p in js_files if p.name.endswith('.min.js')]
        orphaned = []
        for p in min_files:
            rel = str(p.relative_to(static_dir))
            # Skip vendor libraries in plugins/vendor/adminlte folders
            if any(x in rel for x in ['plugins', 'vendor', 'adminlte', 'node_modules', 'dist']):
                continue
            # Skip vendor-only minified files without source
            if p.name in ('dark-mode.min.js', 'sweetalert2.min.js'):
                continue
            name = p.name
            if '.min.js' in name:
                base = name.split('.min.js')[0]
                if '.' in base:
                    base = base.rsplit('.', 1)[0]
                source_path = p.parent / (base + '.js')
                if not source_path.exists():
                    orphaned.append(p.name)
        assert len(orphaned) == 0, f'Orphaned .min.js files: {orphaned[:20]}'

    def test_css_files_source_and_min_pairs(self):
        static_dir = PROJECT_ROOT / 'static'
        css_files = list(static_dir.rglob('*.css'))
        min_files = [p for p in css_files if p.name.endswith('.min.css')]
        orphaned = []
        for p in min_files:
            rel = str(p.relative_to(static_dir))
            if any(x in rel for x in ['plugins', 'vendor', 'adminlte', 'node_modules', 'dist']):
                continue
            if p.name in ('sweetalert2.min.css',):
                continue
            name = p.name
            if '.min.css' in name:
                base = name.split('.min.css')[0]
                if '.' in base:
                    base = base.rsplit('.', 1)[0]
                source_path = p.parent / (base + '.css')
                if not source_path.exists():
                    orphaned.append(p.name)
        assert len(orphaned) == 0, f'Orphaned .min.css files: {orphaned[:20]}'

    def test_no_duplicate_static_file_names(self):
        static_dir = PROJECT_ROOT / 'static'
        names = {}
        for p in static_dir.rglob('*'):
            if p.is_file():
                names.setdefault(p.name, []).append(str(p.relative_to(static_dir)))
        duplicates = {n: paths for n, paths in names.items() if len(paths) > 1}
        # Skip common library files and minified versions
        real_dupes = {}
        for n, paths in duplicates.items():
            if n.endswith(('.min.js', '.min.css', '.js.map', '.css.map', '.min.js.map', '.min.css.map')):
                continue
            if n in ('index.html', 'README.md', 'LICENSE', '.gitignore', 'package.json'):
                continue
            # Skip vendor libraries in adminlte/plugins
            if all('adminlte' in p or 'plugins' in p for p in paths):
                continue
            # Skip tenant and brand assets
            if any('assets\\tenants' in p or 'assets\\brand' in p for p in paths):
                continue
            # Skip .gitkeep files
            if n == '.gitkeep':
                continue
            # Skip sw.js locale collision (service worker vs Swahili moment locale)
            if n == 'sw.js':
                continue
            if len(paths) > 1:
                real_dupes[n] = paths
        assert real_dupes == {}, f'Duplicate static file names: {real_dupes}'

    def test_critical_static_files_exist(self):
        critical = [
            'js/azad-app.js',
            'js/base-helpers.js',
            'css/erp-theme.css',
        ]
        static_dir = PROJECT_ROOT / 'static'
        missing = [f for f in critical if not (static_dir / f).exists()]
        assert missing == [], f'Missing critical static files: {missing}'

    def test_no_empty_static_files(self):
        static_dir = PROJECT_ROOT / 'static'
        empty_files = [str(p.relative_to(static_dir)) for p in static_dir.rglob('*') if p.is_file() and p.stat().st_size == 0 and p.name != '.gitkeep']
        assert empty_files == [], f'Empty static files: {empty_files[:20]}'

    def test_images_have_valid_extensions(self):
        static_dir = PROJECT_ROOT / 'static'
        image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp'}
        invalid = []
        for p in static_dir.rglob('*'):
            if p.is_file() and p.suffix.lower() in image_exts:
                try:
                    with open(p, 'rb') as f:
                        header = f.read(8)
                    if not header:
                        invalid.append(str(p.relative_to(static_dir)))
                except Exception:
                    invalid.append(str(p.relative_to(static_dir)))
        assert invalid == [], f'Invalid image files: {invalid[:20]}'

    def test_vendor_libraries_in_vendor_or_plugins_folder(self):
        static_dir = PROJECT_ROOT / 'static'
        vendor_names = {'jquery', 'bootstrap', 'select2', 'datatables', 'moment', 'lodash', 'axios'}
        misplaced = []
        for p in static_dir.rglob('*.js'):
            if p.is_file() and any(v in p.name.lower() for v in vendor_names):
                rel = str(p.relative_to(static_dir))
                if not any(x in rel for x in ['vendor', 'plugins', 'lib', 'dist']):
                    if 'adminlte' not in rel and 'node_modules' not in rel:
                        misplaced.append(rel)
        assert misplaced == [], f'Vendor JS not in vendor/plugins folder: {misplaced[:20]}'
