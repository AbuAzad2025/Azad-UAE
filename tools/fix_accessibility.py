"""Fix common accessibility errors in HTML/Jinja2 templates."""
import os
import re
from typing import List, Tuple


class AccessibilityFixer:
    def __init__(self, templates_dir: str):
        self.templates_dir = templates_dir
        self.fixed_count = 0
        self.files_changed = set()

    def fix_all(self):
        for root, _, files in os.walk(self.templates_dir):
            for fname in files:
                if not fname.endswith('.html'):
                    continue
                fpath = os.path.join(root, fname)
                self._fix_file(fpath)

    def _fix_file(self, fpath: str):
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        original = content

        # Fix 1: Buttons with only icon, no title
        content = self._fix_icon_buttons(content)

        # Fix 2: Links with only icon, no title
        content = self._fix_icon_links(content)

        # Fix 3: Inputs with adjacent label but no id/for
        content = self._fix_unlabeled_inputs(content)

        # Fix 4: Selects without accessible name
        content = self._fix_unlabeled_selects(content)

        if content != original:
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)
            self.files_changed.add(fpath)

    def _fix_icon_buttons(self, content: str) -> str:
        """Add title to buttons containing only <i> or <span> with icon classes."""
        pattern = re.compile(
            r'(<button\s+[^>]*?)>(\s*)<i\s+class="[^"]*fas\s+fa-([^"\s]+)[^"]*"[^>]*>[^<]*</i>(\s*)</button>',
            re.IGNORECASE
        )

        def _replace_btn(m):
            prefix = m.group(1)
            ws1 = m.group(2)
            icon_name = m.group(3)
            ws2 = m.group(4)
            if 'title=' in prefix.lower():
                return m.group(0)
            # Map common icons to Arabic labels
            label = _icon_to_label(icon_name)
            prefix = prefix.rstrip()
            if prefix.endswith('"') or prefix.endswith("'"):
                prefix += ' title="' + label + '"'
            else:
                prefix += ' title="' + label + '"'
            self.fixed_count += 1
            return prefix + '>' + ws1 + '<i class="fas fa-' + icon_name + '"></i>' + ws2 + '</button>'

        return pattern.sub(_replace_btn, content)

    def _fix_icon_links(self, content: str) -> str:
        """Add title to links containing only icon."""
        pattern = re.compile(
            r'(<a\s+[^>]*?)>(\s*)<i\s+class="[^"]*fas\s+fa-([^"\s]+)[^"]*"[^>]*>[^<]*</i>(\s*)</a>',
            re.IGNORECASE
        )

        def _replace_link(m):
            prefix = m.group(1)
            ws1 = m.group(2)
            icon_name = m.group(3)
            ws2 = m.group(4)
            if 'title=' in prefix.lower():
                return m.group(0)
            label = _icon_to_label(icon_name)
            prefix = prefix.rstrip()
            prefix += ' title="' + label + '"'
            self.fixed_count += 1
            return prefix + '>' + ws1 + '<i class="fas fa-' + icon_name + '"></i>' + ws2 + '</a>'

        return pattern.sub(_replace_link, content)

    def _fix_unlabeled_inputs(self, content: str) -> str:
        """Add accessible name to inputs that lack aria-label/title/placeholder."""
        pattern = re.compile(
            r'(<input\s+[^>]*?name="([^"]+)"[^>]*?)(/?>\s*)',
            re.IGNORECASE
        )

        def _replace(m):
            prefix = m.group(1)
            name = m.group(2)
            close = m.group(3)
            low = prefix.lower()
            if 'aria-label=' in low or 'title=' in low or 'placeholder=' in low:
                return m.group(0)
            # Check if an associated label exists nearby
            label_text = _name_to_label(name)
            prefix = prefix.rstrip()
            if prefix.endswith('/'):
                prefix = prefix[:-1].rstrip() + ' aria-label="' + label_text + '" /'
            else:
                prefix = prefix + ' aria-label="' + label_text + '"'
            self.fixed_count += 1
            return prefix + close

        return pattern.sub(_replace, content)

    def _fix_unlabeled_selects(self, content: str) -> str:
        """Add aria-label to selects without label."""
        pattern = re.compile(
            r'(<select\s+[^>]*?name="([^"]+)"[^>]*?)(>)',
            re.IGNORECASE
        )

        def _replace(m):
            prefix = m.group(1)
            name = m.group(2)
            close = m.group(3)
            if 'aria-label=' in prefix.lower() or 'id=' in prefix.lower():
                return m.group(0)
            aria = 'aria-label="' + _name_to_label(name) + '"'
            prefix = prefix.rstrip()
            prefix += ' ' + aria
            self.fixed_count += 1
            return prefix + close

        return pattern.sub(_replace, content)


def _icon_to_label(icon: str) -> str:
    mapping = {
        'eye': 'عرض',
        'print': 'طباعة',
        'minus': 'طي/توسيع',
        'plus': 'إضافة',
        'edit': 'تعديل',
        'trash': 'حذف',
        'undo': 'تراجع',
        'lock': 'قفل',
        'unlock': 'فتح',
        'search': 'بحث',
        'bars': 'القائمة',
        'times': 'إغلاق',
        'check': 'تأكيد',
        'arrow-left': 'رجوع',
        'arrow-right': 'تقدم',
        'sync': 'تحديث',
        'download': 'تحميل',
        'upload': 'رفع',
        'cog': 'إعدادات',
        'user': 'مستخدم',
        'users': 'مستخدمون',
        'building': 'فرع',
        'warehouse': 'مستودع',
        'box': 'منتج',
        'shopping-cart': 'سلة',
        'file-invoice': 'فاتورة',
        'chart-bar': 'تقرير',
        'calculator': 'حاسبة',
        'coins': 'عملات',
        'book': 'دفتر',
        'vault': 'خزينة',
    }
    return mapping.get(icon, icon.replace('-', ' ').title())


def _name_to_label(name: str) -> str:
    mapping = {
        'employee_id': 'اختر الموظف',
        'branch_id': 'اختر الفرع',
        'department_id': 'اختر القسم',
        'month': 'الشهر',
        'year': 'السنة',
        'currency': 'العملة',
        'account_id': 'اختر الحساب',
        'date_from': 'من تاريخ',
        'date_to': 'إلى تاريخ',
    }
    return mapping.get(name, name.replace('_', ' '))


if __name__ == '__main__':
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates = os.path.join(root, 'templates')
    fixer = AccessibilityFixer(templates)
    fixer.fix_all()
    print(f'Fixed {fixer.fixed_count} issues in {len(fixer.files_changed)} files')
