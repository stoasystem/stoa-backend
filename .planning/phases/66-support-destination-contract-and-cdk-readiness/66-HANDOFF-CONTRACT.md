# Phase 66 Support Handoff Contract

**Status:** Complete
**Created:** 2026-06-07

## Purpose

Define the metadata-only package that admins can use to hand off recovery, rollback, fixture, or release evidence into support workflows.

## Package Shape

Required top-level fields:

| Field | Required | Notes |
|-------|----------|-------|
| `schema_version` | Yes | Start with `v1`. |
| `package_id` | Yes | Opaque generated id. |
| `generated_at` | Yes | ISO-8601 UTC timestamp. |
| `generated_by` | Yes | Admin identity, redacted to support-safe identifier. |
| `reason` | Yes | Operator-provided handoff reason. |
| `destination` | Yes | Manual copy/download by default; direct writes require approved credentials. |
| `evidence_references` | Yes | Recovery job ids, support package ids, release evidence ids, fixture ids, or rollback audit refs. |
| `sections` | Yes | Allowlisted metadata sections. |
| `validation` | Yes | Missing references, skipped sections, privacy result, and status. |
| `audit` | Yes | Correlation id/request id and audit event references. |

## Allowed Sections

- Recovery job summary.
- Recovery target/result aggregate summary.
- Existing support evidence package summary.
- Release evidence summary.
- Safe-fixture status summary.
- Rollback/edit audit reference summary.
- Operator notes after redaction.

## Output Modes

- `preview`: API/UI preview; no package download event required.
- `copy`: UI copy-ready text/markdown; audit as package generated.
- `download`: JSON/Markdown file content returned through backend; audit as package generated.
- `external_write`: future adapter mode; refused in v2.4 unless approved credentials exist.

## Phase 67 Constraints

- Return allowlisted fields only.
- Keep package payload bounded.
- Do not include raw report artifact contents.
- Do not include private storage locations or presigned URLs.
- Include validation failures as structured metadata instead of throwing away partial safe context.

## Existing Shape Alignment

Phase 67 should build on these existing backend shapes:

- `report_recovery_evidence_service.build_export_response` already returns bounded recovery evidence with `exported_at`, `request_id`, `scope`, sanitized filters, jobs, targets, audit summaries, pagination tokens, and a metadata-only privacy block.
- `report_recovery_evidence_service.build_support_package_response` already returns a job-scoped support package with source job linkage, rollup, targets, job/report audit summaries, redacted operator note, pagination tokens, and privacy metadata.
- `release_evidence_service.validate_release_bundle` already validates release evidence bundles and returns sanitized bundles plus privacy denylist results.
- `release_evidence_service.build_fixture_inventory_response` already returns safe-fixture identity, artifact version metadata, report metadata, audit refs, mutation refusal metadata, and privacy validation.

The v2.4 handoff package should compose these safe projections by reference. It should not bypass their redaction helpers or introduce a parallel raw evidence model.
