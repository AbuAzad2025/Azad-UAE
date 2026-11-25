"""Probe regressions found by booting against a populated database.

``.group_by(...).scalar()`` silently calls ``.one()``: as soon as a tenant owns
more than one document code the probe raises MultipleResultsFound and the boot
reports the data set as "not measured" instead of checking it.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestDocumentSequenceProbe:
    def test_multiple_codes_report_the_largest_group(self):
        from utils.seed_manifest_probe import max_document_sequences_per_document_type

        query = MagicMock()
        query.filter.return_value.group_by.return_value.all.return_value = [(1,), (1,), (2,)]
        with (
            patch("utils.seed_manifest_probe._active_tenant_ids", return_value=[1]),
            patch("extensions.db.session.query", return_value=query),
        ):
            assert max_document_sequences_per_document_type() == 2

    def test_empty_tenant_set_reports_zero(self):
        from utils.seed_manifest_probe import max_document_sequences_per_document_type

        with patch("utils.seed_manifest_probe._active_tenant_ids", return_value=[]):
            assert max_document_sequences_per_document_type() == 0
