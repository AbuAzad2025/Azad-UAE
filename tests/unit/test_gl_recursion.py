import pytest
from models.gl import GLAccount


def test_get_children_depth_limit(db_session, sample_tenant):
    accounts = []
    for i in range(13):
        acc = GLAccount(
            tenant_id=sample_tenant.id,
            code=f"DEPTH{i:04d}",
            name=f"Depth {i}",
            type="asset",
            parent_id=accounts[-1].id if accounts else None,
        )
        db_session.add(acc)
        db_session.flush()
        accounts.append(acc)

    with pytest.raises(RecursionError):
        accounts[0].get_children_recursive()


def test_get_children_circular(db_session, sample_tenant):
    a1 = GLAccount(tenant_id=sample_tenant.id, code="CIRC1", name="Circ1", type="asset")
    a2 = GLAccount(tenant_id=sample_tenant.id, code="CIRC2", name="Circ2", type="asset")
    a3 = GLAccount(tenant_id=sample_tenant.id, code="CIRC3", name="Circ3", type="asset")
    db_session.add_all([a1, a2, a3])
    db_session.flush()

    a1.parent_id = a2.id
    a2.parent_id = a3.id
    a3.parent_id = a1.id
    db_session.flush()

    with pytest.raises(ValueError, match="Circular reference detected"):
        a1.get_children_recursive()


def test_get_children_normal(db_session, sample_tenant):
    a1 = GLAccount(tenant_id=sample_tenant.id, code="NORM1", name="Norm1", type="asset")
    a2 = GLAccount(tenant_id=sample_tenant.id, code="NORM2", name="Norm2", type="asset")
    a3 = GLAccount(tenant_id=sample_tenant.id, code="NORM3", name="Norm3", type="asset")
    db_session.add_all([a1, a2, a3])
    db_session.flush()

    a2.parent_id = a1.id
    a3.parent_id = a1.id
    db_session.flush()

    children = a1.get_children_recursive()
    assert len(children) == 2
    assert set(c.id for c in children) == {a2.id, a3.id}
