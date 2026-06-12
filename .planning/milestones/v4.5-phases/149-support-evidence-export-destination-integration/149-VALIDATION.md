# Phase 149 Validation Map

**Phase:** Support Evidence Export Destination Integration  
**Requirement:** SUPPORTINT-02  
**Created:** 2026-06-12

## Validation Goal

Prove the backend can deliver a support-safe package to the approved `internal_queue` path while preserving manual fallback and fail-closed behavior for missing approval, unknown destinations, contract-defined unapproved destinations, privacy failures, and duplicate requests.

## Required Checks

| Check | Requirement coverage | Expected assertion | Automated target |
|-------|----------------------|--------------------|------------------|
| Admin-only delivery route | SUPPORTINT-02 access control | Non-admin request returns 403 and does not read evidence | `tests/test_admin_report_ops.py::test_support_handoff_delivery_is_admin_only` |
| Approved internal queue delivery | Support-safe approved destination path | Approved `internal_queue` request returns `delivery.status == "queued"` and writes metadata-only delivery record | `tests/test_admin_report_ops.py::test_support_handoff_internal_queue_delivery_queues_metadata_only_record` |
| Missing approval refusal | Fail-closed readiness | Missing/false approval returns `delivery.status == "refused"` and no queued/sent delivery record | `tests/test_admin_report_ops.py::test_support_handoff_internal_queue_requires_approval` |
| Privacy failure refusal | Package privacy before delivery | Privacy-failed package returns refused delivery and does not queue | `tests/test_admin_report_ops.py::test_support_handoff_internal_queue_refuses_privacy_failure` |
| Duplicate idempotency | Stable delivery identity | Duplicate identical approved request reuses delivery ID/idempotency key instead of creating a second queued row | `tests/test_admin_report_ops.py::test_support_handoff_internal_queue_idempotent_duplicate` |
| Unknown destination fail-fast | Unknown destinations rejected before evidence access | Unknown delivery destination returns 422 before evidence reads | `tests/test_admin_report_ops.py::test_support_handoff_delivery_unknown_destination_rejects_before_evidence_reads` |
| Contract-defined unapproved refusal | Unapproved destinations recorded as refused | `external_write`, `shared_mailbox`, `zendesk_ticket`, `freshdesk_ticket`, and `helpscout_conversation` skip evidence reads and return/persist redacted refused delivery metadata | `tests/test_admin_report_ops.py::test_support_handoff_delivery_contract_defined_destination_is_refused_without_evidence_reads` |
| Manual fallback regression | Existing fallback preserved | Existing package-route tests for preview/copy/download/external_write/unknown destination still pass | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` |

## Privacy Invariants

Every response and persisted delivery record tested in Phase 149 must exclude:

- raw report HTML or JSON
- `weekly-reports/` object keys
- `json_s3_key`, `html_s3_key`, or generic `s3_key`
- presigned URLs
- authorization headers
- cookies
- API keys
- OAuth or Cognito token markers
- raw provider/customer payloads
- raw package sections serialized as a delivery payload

## Execution Gates

- Focused gate: `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff`
- Wider route gate: `./.venv/bin/pytest -q tests/test_admin_report_ops.py`
- Plan gate: `node /Users/zhdeng/.codex/get-shit-done/bin/gsd-tools.cjs query verify.plan-structure --phase 149-support-evidence-export-destination-integration`

## Acceptance Threshold

Phase 149 cannot complete unless the focused support handoff test gate passes and verifies approved, readiness-refused, privacy-failed, idempotent duplicate, unknown destination fail-fast, contract-defined unapproved refusal, and manual fallback behavior.
