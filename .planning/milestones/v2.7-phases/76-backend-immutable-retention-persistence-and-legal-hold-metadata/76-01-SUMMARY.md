# Phase 76 Summary: Backend Immutable Retention Persistence And Legal Hold Metadata

**Phase:** 76
**Status:** Complete
**Completed:** 2026-06-07

## Completed Work

- Added disabled-by-default immutable audit storage settings.
- Added repository methods for immutable manifest reference persistence and legal hold metadata/audit rows.
- Added admin-only immutable evidence status and persistence endpoints.
- Added admin-only legal hold status and apply/release metadata endpoints.
- Kept immutable persistence fail-closed with `not_configured` when CDK-managed storage configuration is absent.
- Added focused backend tests for authorization, config refusal, configured persistence, legal hold metadata, release semantics, sensitive request ID redaction, persisted metadata sanitization, audit rows, and privacy denylist behavior.

## Verification

- `ruff check src/stoa/services/report_audit_retention_service.py src/stoa/routers/admin.py src/stoa/db/repositories/report_repo.py tests/test_admin_report_ops.py` passed.
- `PYTHONPATH=src .venv/bin/pytest tests/test_admin_report_ops.py -k "audit_retention or immutable or legal_hold"` passed: 15 selected tests.

## Phase 77 Guidance

- Add frontend API types and hooks for the new immutable evidence and legal hold endpoints.
- Reuse existing audit retention reference selection and privacy denylist UI tests.
- Keep old audit-retention panel language distinct from new immutable/legal-hold status, because immutable storage remains `not_configured` until CDK evidence exists.
