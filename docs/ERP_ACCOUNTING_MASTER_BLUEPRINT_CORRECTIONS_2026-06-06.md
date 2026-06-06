# ERP Accounting Master Blueprint — Reconciled Corrections Overlay

**Date:** June 6, 2026
**Status:** Reconciled local/GitHub overlay for `docs/ERP_ACCOUNTING_MASTER_BLUEPRINT.md`
**Source reviewed:** Remote commit `f29aa07` (`docs: add blueprint correction overlay for Jun 6 status`)

## 1. Merge Decision

The remote GitHub commit `f29aa07` added only this correction-overlay file path. Its original content was useful for identifying stale metadata and a stale `ENABLE_DYNAMIC_GL_MAPPING` sentence, but it was based on an older repository state and incorrectly treated Phase 8, Phase 9, and Phase 10 as pending.

Do not cherry-pick or restore the original `f29aa07` text verbatim. It would downgrade completed local work and reintroduce contradictions.

## 2. Corrections Accepted Into The Master Blueprint

The master blueprint now treats the following as authoritative:

- Header and footer metadata are updated to June 6, 2026, Session 7.
- `ENABLE_DYNAMIC_GL_MAPPING` is active for resolved critical concepts, with legacy fallback and validation guards still retained.
- Mandatory service-layer dimension enforcement remains deferred until operational UI flows pass dimensions explicitly.
- Phase 8, Phase 9, and Phase 10 remain completed according to the local implementation commits.
- Phase 7.5 remains partial because the payment-vault separation and Azad 1% online-store fee work has an active handoff and final QA still pending.

## 3. Correct Current Status

| Area | Correct Status |
|------|----------------|
| Phase 7 | Completed |
| Phase 7.5 | Partial / vault handoff active |
| Phase 8 | Completed |
| Phase 9 | Completed |
| Phase 10 | Completed |
| Payment vault | In progress, see `docs/PAYMENT_VAULT_HANDOFF_REPORT_2026-06-06.md` |
| Azad online-store 1% fee | Implemented in code path, pending final QA and reporting/settlement UI decision |

## 4. Required Assistant Guardrail

When reconciling docs, keep this file and the active handoff aligned with the actual local code. Do not mark all work closed while `docs/PAYMENT_VAULT_HANDOFF_REPORT_2026-06-06.md` still lists required vault QA and follow-up work.
