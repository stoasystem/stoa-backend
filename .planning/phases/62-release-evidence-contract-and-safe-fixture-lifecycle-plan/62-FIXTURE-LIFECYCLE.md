# Phase 62 Safe Fixture Lifecycle

**Status:** Complete
**Created:** 2026-06-06

## Approved Fixture

Current approved synthetic non-customer fixture from v2.2:

| Field | Value |
|-------|-------|
| Fixture name | `stoa-safe-fixture-v2-2-rollback-2026-06-06` |
| Parent ID | `safe-fixture-parent-v2-2` |
| Student ID | `safe-fixture-student-v2-2` |
| Week start | `2026-06-01` |
| Purpose | Artifact edit/rollback verification and cleanup evidence |

## Lifecycle States

| State | Meaning | Allowed Operations |
|-------|---------|--------------------|
| `ready` | Fixture exists and current metadata matches expected baseline. | Read-only smoke, approved mutation smoke. |
| `dirty` | Fixture exists but current metadata differs from baseline or previous cleanup is incomplete. | Read-only inspect, cleanup/restore only. |
| `missing` | Fixture cannot be found. | Create/restore only through an approved fixture creation path. |
| `disabled` | Fixture is intentionally unavailable. | Read-only inspect only. |

## Required Evidence

Fixture status evidence must include:

- Fixture name and synthetic IDs.
- Current report status and sanitized artifact version IDs.
- Last known edit/rollback audit references.
- Cleanup/restore outcome.
- Privacy denylist result.
- Request IDs for API calls.
- Operator and timestamp for any approved mutation smoke.

## Refusal Rules

Production mutation tooling must refuse when:

- Fixture name is missing.
- Mutation mode is missing.
- Fixture name is not on the approved list.
- Fixture status is `dirty`, `missing`, or `disabled` and the requested operation is not cleanup/restore.
- Privacy denylist checks fail.
- Any target appears to be customer-owned rather than synthetic.

## Retention And Cleanup

- Preserve versioned fixture artifacts unless cleanup requires a metadata pointer restore.
- Do not delete prior version history during normal cleanup.
- Record whether cleanup restored the report metadata pointer to the baseline.
- Keep fixture evidence metadata-only and committed-safe.

## Emergency Disable

If fixture state becomes ambiguous or unsafe:

1. Mark fixture as `disabled` in the release gate evidence.
2. Stop all mutation smoke.
3. Use read-only API checks to capture current sanitized state.
4. Open a follow-up phase or incident note before re-enabling mutation smoke.

## Phase 63 Implementation Result

- Approved fixture metadata is centralized in `release_evidence_service.APPROVED_FIXTURES`.
- Fixture status inspection reports `ready`, `dirty`, `missing`, or `disabled` without private S3 keys or raw artifact payloads.
- Mutation refusal checks reject missing fixture name, missing mutation mode, unapproved fixtures, non-ready fixture status, and failed privacy checks.
