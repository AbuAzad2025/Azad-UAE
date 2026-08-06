"""Branch service — branch creation and management."""

from __future__ import annotations

import logging

from extensions import db

logger = logging.getLogger(__name__)


class BranchService:
    """Pure business logic for branch operations. Uses flush only — callers manage transactions."""

    @staticmethod
    def create_branch(
        name: str,
        code: str = "",
        city: str = "",
        address: str = "",
        phone: str = "",
        is_main: bool = False,
        tenant_id: int | None = None,
    ):
        """Create a new branch. Returns the created branch (not yet committed)."""
        from models import Branch

        branch = Branch(name=name, code=code, city=city, address=address, phone=phone, is_main=is_main)
        if tenant_id is not None:
            branch.tenant_id = tenant_id
        db.session.add(branch)
        return branch
