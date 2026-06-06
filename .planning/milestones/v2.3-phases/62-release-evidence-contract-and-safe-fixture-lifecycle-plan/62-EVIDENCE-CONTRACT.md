# Phase 62 Release Evidence Contract

**Status:** Complete
**Created:** 2026-06-06

## Purpose

Define the redacted, repository-safe evidence bundle that v2.3 tooling should collect and validate during release gates.

## Bundle Shape

Required top-level fields:

| Field | Required | Notes |
|-------|----------|-------|
| `schema_version` | Yes | Start with `v1`. |
| `milestone` | Yes | Example: `v2.3`. |
| `phase` | Yes | Release phase number when generated. |
| `generated_at` | Yes | ISO-8601 UTC timestamp. |
| `environment` | Yes | `production`, `staging`, or `local`. |
| `backend` | Yes | Backend commit SHA, branch, deploy run ID, Lambda manifest hash, runtime SHA/config summary. |
| `frontend` | Yes | Frontend commit SHA, branch, deploy run ID, build marker summary, route smoke summary. |
| `infra` | Yes | CDK diff classification, deploy run ID if any, stack names, expected drift summary. |
| `api_checks` | Yes | Admin-only request IDs, endpoint summaries, auth/privacy outcome. |
| `browser_smoke` | Yes | Route, account class, read-only guard result, private marker denylist result. |
| `fixture` | Conditional | Required only when approved fixture mutation smoke is performed. |
| `privacy` | Yes | Denylist terms checked, redaction outcome, violation count. |
| `quality_gates` | Yes | Local lint/test/build commands and pass/fail/skipped status. |
| `operator_notes` | No | Redacted freeform notes. |

## Evidence Semantics

- `status` values: `passed`, `failed`, `skipped`, `blocked`.
- Skipped required checks must include `reason`, `owner`, and `follow_up`.
- Failed privacy checks fail the entire bundle.
- Production mutation evidence is invalid unless `fixture.approved_fixture_name` and `fixture.mutation_mode` are present.

## Redaction Denylist

Committed evidence, CLI output intended for docs, API responses, and UI rendering must not include:

- Passwords, auth tokens, refresh tokens, cookies, or Cognito session secrets.
- AWS access keys or secret access keys.
- S3 object keys for private report artifacts.
- Presigned URLs or public artifact URLs.
- Raw report JSON, raw report HTML, or raw artifact payload excerpts.
- Customer-identifying fixture data beyond approved synthetic fixture identifiers.

## Phase 63 Constraints

- Prefer deterministic JSON output that can be pasted into release gate docs.
- Fail closed on missing required fields or denylist hits.
- Avoid network mutation by default; production checks should be read-only unless explicit safe-fixture mutation flags are supplied.
- Store request IDs and deploy run IDs as identifiers, not full response payloads.

## Phase 63 Implementation Result

- `src/stoa/services/release_evidence_service.py` implements the v1 schema validator, redaction denylist, fixture inventory response, and mutation refusal checks.
- `scripts/release_evidence.py` exposes `validate`, `fixture-status`, and `check-mutation` operator commands.
- Admin-only backend endpoints expose release evidence validation and fixture status for Phase 64 UI rendering.
