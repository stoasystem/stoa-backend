# Phase 150 Validation Map

**Phase:** Operator Queue And Handoff Status Visibility  
**Requirement:** SUPPORTINT-03  
**Created:** 2026-06-12

## Validation Goal

Prove operators can inspect recent support handoff delivery activity through admin-only, bounded, metadata-only list/detail APIs and understand lifecycle/retry state without exposing raw packages, artifacts, secrets, or provider payloads.

## Required Checks

| Check | Requirement coverage | Expected assertion | Automated target |
|-------|----------------------|--------------------|------------------|
| Admin-only list/detail | Access control | Non-admin list/detail requests return 403 and do not call delivery repo helpers | `test_support_handoff_delivery_queue_is_admin_only` |
| Recent list filters | Bounded queue visibility | List endpoint passes status, destination, package ID, date range, limit, and decoded token to repo helper | `test_support_handoff_delivery_queue_lists_filtered_metadata` |
| Pre-feed delivery visibility | Recent activity coverage | Existing Phase 149 delivery summaries without feed rows appear through read-through/backfill list coverage | `test_support_handoff_delivery_queue_includes_pre_feed_summaries` |
| Full lifecycle vocabulary | Status visibility | List/detail expose `created`, `queued`, `sent`, `failed`, `refused`, and `retried` records distinctly | `test_support_handoff_delivery_queue_distinguishes_lifecycle_states` |
| Invalid list token | Input validation | Invalid list token returns 400 before repo helper call | `test_support_handoff_delivery_queue_rejects_invalid_token` |
| Detail summary and audit | Handoff detail visibility | Detail endpoint returns summary plus bounded audit events and audit next token | `test_support_handoff_delivery_detail_includes_bounded_audit` |
| Missing detail | Detail safety | Missing delivery ID returns 404 | `test_support_handoff_delivery_detail_404_for_missing_record` |
| Invalid audit token | Input validation | Invalid detail audit token returns 400 before audit query | `test_support_handoff_delivery_detail_rejects_invalid_audit_token` |
| Retry visibility | Explicit retry state | List/detail expose retry metadata and keep refused/privacy/unapproved destinations non-retryable | `test_support_handoff_delivery_retry_visibility_is_read_only` |
| Metadata-only response | Privacy | List/detail/audit responses omit raw payloads, package sections, artifact keys, presigned URLs, headers, cookies, tokens, and secrets | `test_support_handoff_delivery_queue_lists_filtered_metadata` and detail tests |
| Existing support handoff regressions | Compatibility | Existing package/delivery tests remain green | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` |

## Execution Gates

- Plan gate: `node /Users/zhdeng/.codex/get-shit-done/bin/gsd-tools.cjs query verify.plan-structure .planning/phases/150-operator-queue-and-handoff-status-visibility/150-01-PLAN.md`
- Focused gate: `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff`
- Wider route gate: `./.venv/bin/pytest -q tests/test_admin_report_ops.py`
- Lint gate: `./.venv/bin/ruff check src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py src/stoa/services/support_destination_service.py tests/test_admin_report_ops.py`

## Acceptance Threshold

Phase 150 cannot complete unless the focused support handoff test gate passes and the new tests verify admin-only list/detail access, bounded filtering, pre-feed delivery visibility, complete lifecycle state visibility, pagination-token validation, bounded audit detail, explicit retry visibility, and metadata-only outputs.
