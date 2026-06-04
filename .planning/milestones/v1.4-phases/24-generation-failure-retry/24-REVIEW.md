---
phase: 24
phase_name: Generation Failure Retry
status: fixed
reviewed: 2026-06-04
---

# Phase 24 Review: Generation Failure Retry

## Verdict

`fixed`

The initial implementation passed focused tests but had one concurrency blocker and two coverage/privacy warnings. All review items are resolved.

## Findings

| Severity | Finding | Resolution |
|----------|---------|------------|
| BLOCKER | Retry status check was non-atomic; two admin retries could both run generation side effects. | Added `report_repo.try_start_generation_retry`, a conditional DynamoDB update from `generation_failed` to `generation_retrying`; route returns `409` if the claim fails. |
| WARNING | Retry failure text could persist or expose private `weekly-reports/*` artifact keys. | Added error redaction before persistence and response serialization. |
| WARNING | Non-admin retry authorization coverage was missing. | Added a `403` route test proving the retry pipeline is not invoked for parent users. |

## Verification

- `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` - 85 passed.
- `uv run ruff check src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` - passed.
