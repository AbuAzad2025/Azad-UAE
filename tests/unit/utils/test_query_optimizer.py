from __future__ import annotations

from unittest.mock import MagicMock, patch

from utils import query_optimizer as qo


class _Parent:
    __tablename__ = "parents"
    query = MagicMock()
    children = MagicMock()


class _Child:
    __tablename__ = "children"
    parent_id = 1


class TestOptimizeQuery:
    def test_no_relationships_returns_base_query(self):
        result = qo.optimize_query(_Parent)
        assert result is _Parent.query

    def test_joined_strategy(self):
        with patch("utils.query_optimizer.joinedload") as jl:
            qo.optimize_query(_Parent, relationships=["children"], strategy="joined")
        jl.assert_called_once()

    def test_select_strategy(self):
        with patch("utils.query_optimizer.selectinload") as sl:
            qo.optimize_query(_Parent, relationships=["children"], strategy="select")
        sl.assert_called_once()

    def test_subquery_strategy(self):
        with patch("utils.query_optimizer.subqueryload") as sql:
            qo.optimize_query(_Parent, relationships=["children"], strategy="subquery")
        sql.assert_called_once()


class TestPaginateOptimized:
    def test_paginate_forwards_args(self):
        query = MagicMock()
        qo.paginate_optimized(query, page=2, per_page=10)
        query.paginate.assert_called_once_with(page=2, per_page=10, error_out=False, max_per_page=100)


class TestBatchFetch:
    def test_batch_fetch_maps_by_id(self):
        model = MagicMock()
        item_a = MagicMock(id=1)
        item_b = MagicMock(id=2)
        chain = MagicMock()
        chain.filter.return_value.all.return_value = [item_a, item_b]
        model.query = chain
        result = qo.batch_fetch(model, [1, 2])
        assert result[1] is item_a
        assert result[2] is item_b

    def test_batch_fetch_with_relationships(self):
        model = MagicMock()
        item = MagicMock(id=5)
        chain = MagicMock()
        chain.filter.return_value.options.return_value.all.return_value = [item]
        model.query = chain
        with patch("utils.query_optimizer.joinedload"):
            result = qo.batch_fetch(model, [5], relationships=["children"])
        assert result[5] is item


class TestPrefetchRelated:
    def test_empty_instances(self):
        assert qo.prefetch_related([], "children", MagicMock()) == []

    def test_prefetch_attaches_related(self):
        parent = MagicMock(id=1)
        parent.__tablename__ = "parent"
        child = MagicMock(parent_id=1)
        related_model = MagicMock()
        chain = MagicMock()
        chain.filter.return_value.all.return_value = [child]
        related_model.query = chain
        result = qo.prefetch_related([parent], "children", related_model)
        assert result[0]._prefetched_children == [child]

    def test_prefetch_missing_foreign_key_bucket(self):
        parent = MagicMock(id=9)
        parent.__tablename__ = "parent"
        related_model = MagicMock()
        chain = MagicMock()
        chain.filter.return_value.all.return_value = []
        related_model.query = chain
        result = qo.prefetch_related([parent], "children", related_model)
        assert result[0]._prefetched_children == []
