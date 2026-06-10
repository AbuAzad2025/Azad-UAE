import os
class TestSupportSplit:
    def test_support_includes_partials(self):
        path = 'templates/support.html'
        with open(path, encoding='utf-8') as f:
            content = f.read()
        assert '{% include' in content, 'support.html should contain at least one {% include %}'
    def test_support_partials_exist(self):
        pdir = 'templates/partials/support'
        files = os.listdir(pdir)
        assert len(files) > 0, 'at least one partial should exist in templates/partials/support/'
