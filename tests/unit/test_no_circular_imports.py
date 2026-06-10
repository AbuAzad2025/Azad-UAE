import pytest

class TestNoCircularImports:
    def test_circular_import_resolved(self):
        from models._constants import GL_CONCEPT_REGISTRY
        assert GL_CONCEPT_REGISTRY['AR']['meaning'] == 'Accounts Receivable'
