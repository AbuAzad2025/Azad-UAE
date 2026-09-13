"""Cov5: supplier_service — branch-label loop skips out-of-scope rows."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_branch_labels_skips_rows_outside_scope(mocker, db_session, sample_tenant, sample_supplier):
    from services import supplier_service as ss

    sess = MagicMock()
    sess.session.query.return_value.filter.return_value.all.side_effect = [[(424242, 7)], []]
    mocker.patch.object(ss, "db", sess)
    out = ss.SupplierService.supplier_branch_labels([sample_supplier.id])
    assert out == {sample_supplier.id: []}
