Cleanup: remove old audit reports, fix owner template i18n, organize scripts

- Delete 45+ stale audit reports, docs, and temporary .md files
  Kept only essential docs: AGENTS.md, CHANGELOG, CONTRIBUTING,
  SECURITY, MIGRATIONS, README, and core accounting/deployment docs.
- Fix broken Jinja syntax in owner templates: { t('...') } -> {{ t('...') }}
- Add missing translation keys to utils/i18n.py
- Remove redundant instructional paragraphs from owner/dashboard.html
- Delete orphaned templates: payments/*.html, sales/print.html,
  templates/public/demo.html, templates/offline.html
- Organize loose scripts into scripts/audit/, scripts/dev/, scripts/seed/
- Update .gitignore to ignore temp maintenance outputs and screenshots

All tests pass: 22 passed, 4 skipped.

Generated with Devin (https://cli.devin.ai/docs)
Co-Authored-By: Devin <158243242+devin-ai-integration[bot]@users.noreply.github.com>
