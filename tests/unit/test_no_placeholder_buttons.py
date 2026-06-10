from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestNoPlaceholderButtons:
    def test_no_placeholder_buttons_in_templates(self):
        templates_dir = PROJECT_ROOT / 'templates'
        placeholder_texts = [
            'coming soon', 'not implemented', 'placeholder',
            'click here', 'todo', 'wip', 'work in progress',
            'under construction', 'dummy', 'fake',
            'temporary', 'temp', 'draft', 'prototype',
            'mock', 'stub', 'fixme', 'fix me', 'hack',
            'quick fix', 'workaround',
        ]
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir))
            buttons = re.findall(r'<button[^>]*>.*?</button>', text, re.IGNORECASE | re.DOTALL)
            for btn in buttons:
                btn_text = re.sub(r'<[^>]+>', '', btn).strip().lower()
                if not btn_text:
                    continue
                for pt in placeholder_texts:
                    if btn_text == pt or btn_text.startswith(pt + ' ') or btn_text.endswith(' ' + pt):
                        issues.append(f'{rel}: placeholder button "{btn_text}"')
                        break
        assert issues == [], f'Placeholder buttons found: {issues[:30]}'

    def test_no_empty_button_tags_in_templates(self):
        templates_dir = PROJECT_ROOT / 'templates'
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir))
            buttons = re.findall(r'<button[^>]*>.*?</button>', text, re.IGNORECASE | re.DOTALL)
            for btn in buttons:
                inner = re.sub(r'<[^>]+>', '', btn).strip()
                has_icon = bool(re.search(r'<i[\s>]|fa[\s-]|fas\s|far\s|fal\s|fab\s|mdi[\s-]|material[\s-]', btn, re.IGNORECASE))
                has_img = '<img' in btn.lower()
                has_svg = '<svg' in btn.lower()
                has_aria_label = 'aria-label' in btn.lower() or 'title=' in btn.lower()
                is_bootstrap_close = 'btn-close' in btn.lower()
                if not inner and not has_icon and not has_img and not has_svg and not has_aria_label and not is_bootstrap_close:
                    issues.append(f'{rel}: truly empty button (no text, icon, or label)')
                    break
        assert issues == [], f'Truly empty buttons found: {issues[:30]}'

    def test_no_placeholder_anchor_tags(self):
        templates_dir = PROJECT_ROOT / 'templates'
        placeholder_texts = [
            'coming soon', 'not implemented', 'placeholder',
            'click here', 'todo', 'wip', 'work in progress',
            'under construction', 'dummy', 'fake',
            'temporary', 'temp', 'draft', 'prototype',
            'mock', 'stub', 'fixme', 'fix me', 'hack',
            'quick fix', 'workaround',
        ]
        issues = []
        for path in templates_dir.rglob('*.html'):
            text = path.read_text(encoding='utf-8', errors='ignore')
            rel = str(path.relative_to(templates_dir))
            anchors = re.findall(r'<a[^>]*>.*?</a>', text, re.IGNORECASE | re.DOTALL)
            for a in anchors:
                a_text = re.sub(r'<[^>]+>', '', a).strip().lower()
                for pt in placeholder_texts:
                    if a_text == pt or a_text.startswith(pt + ' ') or a_text.endswith(' ' + pt):
                        issues.append(f'{rel}: placeholder anchor "{a_text}"')
                        break
        assert issues == [], f'Placeholder anchors found: {issues[:30]}'

