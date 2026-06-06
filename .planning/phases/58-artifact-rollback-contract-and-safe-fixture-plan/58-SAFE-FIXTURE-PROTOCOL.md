# Phase 58 Safe Fixture Protocol

**Status:** Accepted for Phase 59 harness implementation
**Scope:** v2.2 production artifact mutation smoke

## Goal

Production artifact mutation smoke can exercise artifact edit and rollback behavior only against a named non-customer fixture, with explicit mutation mode and cleanup/restore evidence.

## Fixture Requirements

A safe fixture must be:

- Non-customer and clearly named.
- Owned by the project/admin smoke process.
- Isolated from real parent/student customer data.
- Backed by report metadata and private artifacts that can be edited and restored.
- Documented in smoke evidence by fixture name and redacted IDs only.

The fixture protocol must not commit or print:

- Passwords, tokens, or session secrets.
- Private S3 keys.
- Presigned URLs.
- Raw report JSON.
- Raw unreviewed HTML.

## Harness Refusal Rules

The production mutation harness must refuse to run unless all are true:

1. `STOA_SAFE_FIXTURE_NAME` or equivalent fixture name argument is present.
2. Explicit mutation mode is present, for example `--mutate-safe-fixture`.
3. API base is the expected production API or an explicitly provided target.
4. Admin credentials come from the approved secret-backed path.
5. Fixture lookup confirms non-customer fixture identity before mutation.

Read-only production smoke remains the default.

## Required Smoke Sequence

1. Load approved admin credentials from the secret-backed path.
2. Resolve fixture by explicit fixture name.
3. Capture sanitized initial artifact version metadata.
4. Create an artifact edit preview using a bounded, reversible test value.
5. Apply the artifact edit and record sanitized new version metadata and request IDs.
6. Create a rollback preview targeting the prior version.
7. Apply rollback and record sanitized rollback metadata and request IDs.
8. Confirm the final current artifact version matches the initial version or an explicitly documented restored state.
9. Confirm route responses and evidence output contain no private marker hits.

## Cleanup/Restore Evidence

Evidence must include:

- Fixture name.
- Production API base.
- Admin email domain only.
- Request IDs for preview/apply/rollback calls.
- Initial, edited, and restored artifact version IDs.
- Audit references or action names.
- `mutationAttempted: true`.
- `cleanupPassed: true` or explicit failure details.
- Privacy denylist result.

If cleanup fails, the harness must:

- Stop further mutation.
- Record the failure with request IDs.
- Surface the fixture name and sanitized version IDs needed for manual restoration.
- Avoid printing private keys or raw payloads.

## Phase 59 Harness Notes

- Prefer a script under `scripts/` if it is intended to be maintained, or `/private/tmp` if it is release-only evidence.
- Tests should cover refusal behavior without production credentials.
- Production Phase 61 should run read-only smoke first, then safe-fixture mutation smoke only when the explicit fixture configuration is present.
