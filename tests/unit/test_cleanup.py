import os

class TestCleanup:
    def test_no_bak_file(self):
        assert not os.path.exists("templates/base.html.bak")
