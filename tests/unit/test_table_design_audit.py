from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestTableDesignAudit:
    def test_tables_have_thead_with_headers(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        skip = ['print', 'view', 'receipt', 'statement', 'balance_sheet', 'income_statement', 'cash_flow', 'monitoring', 'pos', 'ledger', 'create', 'edit', 'import', 'owner', 'vat_return', 'payment_vault', 'store/admin']
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir)).lower().replace('\\', '/')
            if any(p in rel for p in skip):
                continue
            tables = re.findall(r'<table[^>]*>.*?</table>', text, re.IGNORECASE | re.DOTALL)
            for table in tables:
                if '<thead' not in table.lower():
                    issues.append(f'{rel}: table without <thead>')
                    break
                ths = re.findall(r'<th[^>]*>.*?</th>', table, re.IGNORECASE | re.DOTALL)
                empty_ths = [th for th in ths if not re.sub(r'<[^>]+>', '', th).strip()]
                if empty_ths:
                    issues.append(f'{rel}: table with empty <th> headers')
                    break
        assert issues == [], f'Table header issues: {issues[:30]}'

    def test_no_empty_table_headers(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        skip = ['print', 'view', 'receipt', 'statement', 'balance_sheet', 'income_statement', 'cash_flow', 'monitoring', 'pos', 'ledger', 'create', 'edit', 'import', 'owner', 'vat_return', 'payment_vault', 'store/admin']
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir)).lower().replace('\\', '/')
            if any(p in rel for p in skip):
                continue
            headers = re.findall(r'<th[^>]*>.*?</th>', text, re.IGNORECASE | re.DOTALL)
            for th in headers:
                inner = re.sub(r'<[^>]+>', '', th).strip()
                if not inner and 'scope=' not in th.lower():
                    issues.append(f'{rel}: empty <th> tag')
                    break
        assert issues == [], f'Empty table headers: {issues[:30]}'

    def test_filter_inputs_have_labels_or_placeholders(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir))
            inputs = re.findall(r'<input[^>]*>', text, re.IGNORECASE)
            for inp in inputs:
                is_filter = any(k in inp.lower() for k in ['search', 'filter', 'query', 'keyword'])
                if is_filter:
                    has_placeholder = 'placeholder=' in inp.lower()
                    has_aria_label = 'aria-label=' in inp.lower()
                    has_label = bool(re.search(r'<label[^>]*>.*?' + re.escape(inp) + r'.*?</label>', text, re.IGNORECASE | re.DOTALL))
                    if not has_placeholder and not has_aria_label and not has_label:
                        issues.append(f'{rel}: filter input without label/placeholder')
                        break
        assert issues == [], f'Filter inputs missing labels: {issues[:30]}'

    def test_select_dropdowns_have_labels(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir))
            selects = re.findall(r'<select[^>]*>.*?</select>', text, re.IGNORECASE | re.DOTALL)
            for sel in selects:
                sel_tag = sel.split('>')[0] + '>'
                has_id = 'id=' in sel_tag.lower()
                has_aria_label = 'aria-label=' in sel_tag.lower()
                has_name = 'name=' in sel_tag.lower()
                options = re.findall(r'<option[^>]*>.*?</option>', sel, re.IGNORECASE | re.DOTALL)
                empty_options = [opt for opt in options if not re.sub(r'<[^>]+>', '', opt).strip()]
                if empty_options and len(options) > 1:
                    issues.append(f'{rel}: select with empty option(s)')
                    break
                if has_name and not has_id and not has_aria_label:
                    name_val = re.search(r'name=["\']([^"\']+)["\']', sel_tag, re.IGNORECASE)
                    if name_val:
                        name_str = name_val.group(1)
                        # Skip common non-labeled selects
                        if any(x in name_str for x in ['variant', 'quantity', 'qty', 'size', 'color', 'lang', 'locale', 'theme', 'rating']):
                            continue
                        label_pattern = r'<label[^>]*for=["\'][^"\']*' + re.escape(name_str) + r'[^"\']*["\']'
                        if not re.search(label_pattern, text, re.IGNORECASE):
                            issues.append(f'{rel}: select without label (name={name_str})')
                            break
        assert issues == [], f'Select dropdown issues: {issues[:30]}'

    def test_no_placeholder_options_in_selects(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        placeholder_options = ['choose', 'select', '---', '...', 'option', 'pick', 'none', 'all']
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir))
            selects = re.findall(r'<select[^>]*>.*?</select>', text, re.IGNORECASE | re.DOTALL)
            for sel in selects:
                options = re.findall(r'<option[^>]*>.*?</option>', sel, re.IGNORECASE | re.DOTALL)
                for opt in options:
                    opt_text = re.sub(r'<[^>]+>', '', opt).strip().lower()
                    for po in placeholder_options:
                        if opt_text == po or opt_text.startswith(po + ' ') or opt_text.endswith(' ' + po):
                            issues.append(f'{rel}: placeholder option "{opt_text}"')
                            break
        assert issues == [], f'Placeholder options found: {issues[:30]}'

    def test_table_rows_have_consistent_columns(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        skip = ['print', 'view', 'receipt', 'statement', 'report', 'monitoring', 'pos', 'owner']
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir)).lower().replace('\\', '/')
            if any(p in rel for p in skip):
                continue
            tables = re.findall(r'<table[^>]*>.*?</table>', text, re.IGNORECASE | re.DOTALL)
            for table in tables:
                tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', table, re.IGNORECASE | re.DOTALL)
                body = tbody_match.group(1) if tbody_match else table
                rows = re.findall(r'<tr[^>]*>.*?</tr>', body, re.IGNORECASE | re.DOTALL)
                if len(rows) > 1:
                    col_counts = []
                    for row in rows:
                        cells = re.findall(r'<t[dh][^>]*>.*?</t[dh]>', row, re.IGNORECASE | re.DOTALL)
                        has_colspan = bool(re.search(r'colspan', row, re.IGNORECASE))
                        if not has_colspan:
                            col_counts.append(len(cells))
                    if col_counts and max(col_counts) != min(col_counts) and max(col_counts) > 0:
                        if max(col_counts) - min(col_counts) > 1:
                            issues.append(f'{rel}: inconsistent column counts ({min(col_counts)}-{max(col_counts)})')
                            break
        assert issues == [], f'Inconsistent table columns: {issues[:30]}'
