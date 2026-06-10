import os
class TestPrintPartials:
    def test_print_styles_partial_exists(self):
        path = 'templates/partials/print_styles.html'
        assert os.path.isfile(path), f'{path} does not exist'
    def test_print_styles_has_at_page(self):
        path = 'templates/partials/print_styles.html'
        with open(path, encoding='utf-8') as f:
            content = f.read()
        assert '@page' in content or 'margin' in content
