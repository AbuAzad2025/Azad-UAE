"""Verify model relationship definitions match FK columns."""
import pytest
from sqlalchemy import inspect
from models import Tenant, StorePaymentMethod, CardPayment, Donation
from models.ai import AiMemory, AiInteraction, AiExpertise


TABLE_MODEL_MAP = {}


def _get_model_for_table(table_name):
    if not TABLE_MODEL_MAP:
        for cls in (Tenant, AiMemory, AiInteraction, AiExpertise,
                    StorePaymentMethod, CardPayment, Donation):
            TABLE_MODEL_MAP[cls.__tablename__] = cls
        from models import User
        TABLE_MODEL_MAP["users"] = User
    return TABLE_MODEL_MAP.get(table_name)


def _get_fk_target_tables(cls):
    targets = set()
    for col in cls.__table__.columns:
        for fk in col.foreign_keys:
            targets.add(fk.column.table.name)
    return targets


def test_tenant_has_relationship():
    assert len(Tenant.__mapper__.relationships) > 0


@pytest.mark.parametrize("model_cls", [
    Tenant, AiMemory, AiInteraction, AiExpertise,
    StorePaymentMethod, CardPayment, Donation,
])
def test_fk_relationships_exist(model_cls):
    fk_tables = _get_fk_target_tables(model_cls)
    rels = list(model_cls.__mapper__.relationships)
    for table_name in fk_tables:
        target_cls = _get_model_for_table(table_name)
        assert target_cls is not None, f"No model class for table '{table_name}'"
        has_rel = any(
            rel.mapper.class_ is target_cls
            for rel in rels
        )
        assert has_rel, (
            f"{model_cls.__name__} has FK to '{table_name}' ({target_cls.__name__}) "
            f"but no relationship targeting {target_cls.__name__}"
        )
