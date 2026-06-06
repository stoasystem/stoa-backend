# Phase 66 Destination Policy And Privacy Model

**Status:** Planned
**Created:** 2026-06-07

## Destination Modes

| Mode | v2.4 Status | Behavior |
|------|-------------|----------|
| `preview` | Allowed | Generate redacted package preview for admin review. |
| `copy` | Allowed | Return copy-ready package text/markdown to the authenticated admin UI. |
| `download` | Allowed | Return redacted package JSON/Markdown for local operator download. |
| `external_write` | Refused by default | Requires approved connector or secret-backed credential path. |

## Refusal Rules

Direct external destination writes must be refused when:

- No approved connector is configured.
- No secret-backed credential path is approved.
- Destination type is unknown.
- Package privacy validation fails.
- Evidence references are missing or outside the admin-authorized scope.
- Operator reason is missing.

## Privacy Denylist

Handoff packages, API responses, UI rendering, logs, and committed evidence must not include:

- Passwords, auth tokens, refresh tokens, cookies, Cognito session secrets, AWS access keys, or secret access keys.
- S3 object keys for private report artifacts.
- Presigned URLs or public artifact URLs.
- Raw report JSON, raw report HTML, or raw artifact payload excerpts.
- Customer data beyond approved support-safe identifiers and aggregate metadata.

## Audit Requirements

Audit metadata should include:

- Operator id.
- Reason.
- Destination mode.
- Package id and schema version.
- Evidence reference ids.
- Validation result.
- Refusal reasons when applicable.
- Correlation id/request id.

Audit metadata must not store raw package payloads when operator notes or customer context could exceed allowlisted identifiers.
