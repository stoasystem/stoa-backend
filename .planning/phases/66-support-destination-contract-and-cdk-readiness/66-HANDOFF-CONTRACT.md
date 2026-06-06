# Phase 66 Support Handoff Contract

**Status:** Planned
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
