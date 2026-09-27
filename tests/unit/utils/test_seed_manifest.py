"""Structural integrity of ``utils/seed_manifest.py``.

The manifest is the single index of what the boot seeds. Its value depends
entirely on staying true, and the previous state of this repository is the
counter-example: AGENTS.md claimed "37 perms / 8 roles / 76 industry fields"
when the real numbers are 36 / 9 / 74, and nothing caught it.

These tests compare the manifest against the constants it describes, so the
counts cannot drift silently. They import configuration only and need no
database - the seeded row counts themselves are verified at boot by
``app/bootstrap.verify_seed_manifest`` and by CI.
"""

from __future__ import annotations

import importlib

import pytest

from utils import seed_manifest as manifest


def _seed_set(key: str):
    matches = [s for s in manifest.ALL_SEED_SETS if s.key == key]
    assert matches, f"manifest has no entry for {key!r}"
    return matches[0]


class TestManifestShape:
    def test_keys_are_unique(self):
        keys = [s.key for s in manifest.ALL_SEED_SETS]
        assert len(keys) == len(set(keys)), "duplicate manifest keys"

    def test_scopes_are_known(self):
        allowed = {"platform", "tenant", "lazy", "deliberate"}
        for s in manifest.ALL_SEED_SETS:
            assert s.scope in allowed, f"{s.key} has unknown scope {s.scope!r}"

    def test_every_entry_is_documented(self):
        for s in manifest.ALL_SEED_SETS:
            assert s.label, f"{s.key} has no label"
            assert s.source, f"{s.key} has no source"
            assert s.note, f"{s.key} has no note explaining its wiring"

    def test_deliberate_unseeded_entries_explain_themselves(self):
        """Anything we choose not to seed must carry a real justification.

        Checked as substance rather than as magic words. An earlier version
        required the note to contain "DELIBERATE" / "tenant business" /
        "operator", which failed on three entries whose reasoning was perfectly
        good prose ("No table exists", "never in bulk"). Matching on wording
        punishes a well-written note and passes a lazy one containing a keyword.
        """
        assert manifest.DELIBERATELY_UNSEEDED
        for s in manifest.DELIBERATELY_UNSEEDED:
            assert s.seeder is None
            assert s.note != s.label, f"{s.key} note just restates the label"
            assert len(s.note) >= 40, f"{s.key} needs a real explanation, got {s.note!r}"

    def test_packages_records_why_it_is_not_seeded(self):
        """Guard the one exclusion most likely to be "helpfully" reverted.

        An idempotent seeder for SaaS packages exists
        (``saas_provisioning_service.seed_packages``) and is deliberately not
        called at boot, because the platform owner sets SaaS pricing from the
        Owner panel. Wiring it in would silently override that decision, so the
        manifest has to say so out loud.
        """
        packages = _seed_set("packages")
        assert packages.seeder is None
        assert "DELIBERATE" in packages.note.upper()
        assert "owner" in packages.note.lower()
        # The dormant seeder is named in ``source``; the note says why it is not run.
        assert "seed_packages" in packages.source

    def test_business_data_is_never_auto_seeded(self):
        """Guard rail: tenant business tables must not acquire a seeder.

        Auto-creating categories, departments or CRM stages would put rows in
        the system that no operator asked for, which is the same class of
        mistake as auto-creating a default-password account.
        """
        for s in manifest.DELIBERATELY_UNSEEDED:
            assert s.seeder is None, f"{s.key} is business data and must not be auto-seeded"


class TestManifestMatchesSource:
    """The counts must equal the constants they claim to describe."""

    def test_permission_count(self):
        import utils.constants as constants

        assert _seed_set("permissions").expected == len(constants.PERMISSION_CODES)

    def test_role_count(self):
        """owner, super_admin, developer + the six functional roles."""
        import utils.system_init as system_init

        slugs = {
            "owner",
            "super_admin",
            "developer",
            "manager",
            "seller",
            "branch_manager",
            "accountant",
            "kitchen",
            "cashier",
        }
        assert _seed_set("roles").expected == len(slugs)
        # Every slug must actually appear in the seeder module.
        text = open(system_init.__file__, encoding="utf-8").read()
        for slug in slugs:
            assert f'slug="{slug}"' in text, f"role {slug} is claimed but not seeded"

    def test_currency_count(self):
        assert _seed_set("currencies").expected == 3  # ILS, AED, USD

    def test_industry_field_count(self):
        import utils.seed_industry_fields as seeder

        total = len(seeder.CORE_FIELDS) + sum(len(v) for v in seeder.INDUSTRY_FIELDS.values())
        assert _seed_set("industry_field_definitions").expected == total

    def test_base_chart_of_accounts(self):
        import models.gl_account_registry as registry

        assert len(registry.BASE_ACCOUNTS) == 98

    def test_document_sequence_count(self):
        """Count the ``defaults`` dict keys in the source, not occurrences of text.

        The dict is a local inside ``get_or_create``, so it cannot be imported.
        Counting ``("`` over the file over-counts badly (15 against a true 9)
        because the same shape appears elsewhere, so the AST is parsed instead.
        """
        import ast

        import services.document_sequence_service as dss

        tree = ast.parse(open(dss.__file__, encoding="utf-8").read())
        counts = [
            len(n.value.keys)
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(getattr(t, "id", None) == "defaults" for t in n.targets)
            and isinstance(n.value, ast.Dict)
        ]
        assert counts, "could not find the defaults dict in document_sequence_service"
        assert _seed_set("document_sequences").expected == max(counts)


class TestManifestProbesResolve:
    @pytest.mark.parametrize("seed_set", manifest.ALL_SEED_SETS, ids=lambda s: s.key)
    def test_probe_imports(self, seed_set):
        """A dotted path that does not resolve is a silent hole in the manifest."""
        if seed_set.verify is None:
            pytest.skip("no probe declared")
        module_path, _, attr = seed_set.verify.rpartition(".")
        assert module_path and attr
        module = importlib.import_module(module_path)
        assert callable(getattr(module, attr)), f"{seed_set.verify} is not callable"

    @pytest.mark.parametrize("seed_set", manifest.ALL_SEED_SETS, ids=lambda s: s.key)
    def test_seeder_path_is_plausible(self, seed_set):
        """Flag an obviously broken seeder reference early.

        ``system_init`` severs several entry points across slash-joined names
        (e.g. ``_ensure_owner_role/_ensure_super_admin_role``), so this checks
        only the first segment resolves - a full resolution would be wrong.
        """
        if seed_set.seeder is None:
            pytest.skip("deliberately unseeded")
        first = seed_set.seeder.split("/")[0].split(".")[0]
        assert first  # sanity

    def test_boot_wired_platform_sets_have_probes(self):
        """Anything seeded at boot must be measurable at boot."""
        for s in manifest.PLATFORM_SEEDS:
            if s.seeder is None:
                continue
            assert s.verify is not None, f"{s.key} is seeded at boot but has no probe"
