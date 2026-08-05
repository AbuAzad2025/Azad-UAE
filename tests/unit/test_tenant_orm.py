"""Regression guards for the tenant isolation criteria builder.

These guard against the SQLAlchemy 2.0.51 lambda-tracking regression in
``_criteria_for_model``: when the platform owner operates with no active
tenant (``effective_tid == 0``), a lambda that branches on the closure
variable produced ``WHERE tenant_id = 0`` (hiding every ``tenant_id IS
NULL`` platform row) instead of the intended ``WHERE true``.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, with_loader_criteria

import pytest


class _StubModel:
    tenant_id = None


class _GuardBase(DeclarativeBase):
    pass


class _GuardVault(_GuardBase):
    __tablename__ = "tenant_orm_guard_vault"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, nullable=True)


class TestPlatformOwnerCriteria:
    """``effective_tid == 0`` must yield an unrestricted (show-all) predicate."""

    @pytest.fixture(autouse=True)
    def _platform_owner(self, mocker):
        # Simulate the platform-owner, no-active-tenant request context that
        # ``before_request`` produces when the owner clears their tenant switch.
        # ``_criteria_for_model`` imports ``is_platform_owner`` lazily from
        # ``utils.tenanting``, so patch it there.
        mocker.patch("utils.tenanting.is_platform_owner", return_value=True)

    def test_criteria_is_unrestricted(self):
        from utils.tenant_orm import _criteria_for_model

        crit = _criteria_for_model(None)
        sql = str(crit(_StubModel))
        assert sql == "true", f"expected unrestricted predicate, got {sql!r}"

    def test_criteria_does_not_produce_tenant_id_eq_zero(self):
        from utils.tenant_orm import _criteria_for_model

        crit = _criteria_for_model(None)
        stmt = select(_GuardVault).options(
            with_loader_criteria(_GuardVault, crit, include_aliases=True)
        )
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id = 0" not in compiled
        assert "WHERE true" in compiled

    def test_platform_rows_remain_visible(self):
        from utils.tenant_orm import _criteria_for_model

        crit = _criteria_for_model(None)
        scoped = select(_GuardVault).options(
            with_loader_criteria(_GuardVault, crit, include_aliases=True)
        )
        engine = create_engine("sqlite:///:memory:")
        _GuardBase.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(_GuardVault(tenant_id=None))
            s.commit()
            rows = s.execute(scoped).scalars().all()
        assert len(rows) == 1, "platform row (tenant_id IS NULL) must stay visible"
