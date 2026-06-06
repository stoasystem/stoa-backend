# Requirements: v2.2 Report Artifact Rollback And Safe Fixture Verification

**Milestone:** v2.2
**Status:** Active
**Created:** 2026-06-06

## Goal

Admins can safely roll back report artifact versions and production verification can exercise artifact mutation only through a named non-customer safe fixture with cleanup evidence.

## Requirements

### ROLLBACK-01 Artifact Rollback Contract And CDK Readiness

Implementers have a precise artifact rollback contract and infrastructure decision before adding rollback mutation code.

Acceptance criteria:

- Contract defines rollback source, target version, current version checks, operator reason requirements, audit actions, and rollback outcome metadata.
- Contract states rollback updates current report artifact pointers without deleting prior versioned artifacts.
- Privacy model proves frontend receives only sanitized version/rollback metadata and never private S3 keys, presigned URLs, raw JSON, raw unreviewed HTML, or artifact payloads.
- CDK readiness classifies whether existing reports bucket/IAM/table resources are sufficient or exactly what CDK change is required.

### ROLLBACK-02 Backend Artifact Rollback Preview And Apply APIs

Admins can preview and apply a rollback from the current report artifact version to a previous artifact version through backend APIs.

Acceptance criteria:

- Rollback preview and apply APIs require admin authorization.
- Rollback preview binds to parent id, student id, week start, current report id, current artifact version, target artifact version, editor, and reason.
- Rollback apply rejects stale source reports, stale current artifact metadata, missing target versions, and attempts to roll back to the already-current version.
- Rollback apply updates report metadata to point at the target artifact version only after validation passes.
- Rollback responses return sanitized rollback/version metadata only.

### ROLLBACK-03 Rollback Audit And Safety Evidence

Artifact rollbacks produce append-only audit evidence and support-safe rollback metadata.

Acceptance criteria:

- Audit includes editor, reason, rollback preview id, source current artifact version, target artifact version, before/after metadata, validation result, source/apply timestamps, and correlation ID.
- Audit remains metadata-only and redacted.
- Existing report audit APIs show artifact rollback events.
- Rollback metadata supports operator follow-up without exposing private S3 keys or raw artifact payloads to the frontend.

### FIXTURE-01 Named Safe Artifact Fixture Protocol And Harness

Production artifact mutation verification uses only a named non-customer fixture with cleanup evidence.

Acceptance criteria:

- Safe fixture protocol defines fixture identity, ownership, allowed mutation paths, cleanup steps, and evidence fields before production mutation.
- Fixture harness can create or locate a non-customer report artifact fixture without exposing secrets or private artifact keys in committed artifacts.
- Fixture cleanup confirms final report state and removes or restores any temporary fixture artifacts needed for the smoke.
- Production mutation smoke refuses to run without an explicit fixture name and explicit mutation mode.

### UI-09 Admin Artifact Rollback UI

Admin report operations UI supports artifact rollback preview and apply controls.

Acceptance criteria:

- UI exposes rollback controls only for selected reports with rollback-eligible artifact metadata.
- UI distinguishes rollback preview from rollback apply mutation.
- UI requires an operator reason before rollback preview/apply.
- UI shows sanitized current/target version metadata, validation state, apply outcome, and audit reference.
- UI denylist remains clean for private artifact markers.
- Playwright covers rollback preview/apply flow, stale/error states, and privacy denylist.

### VERIFY-05 v2.2 Release Gate And Safe Fixture Verification

v2.2 closes with release and live verification evidence for rollback and named safe-fixture mutation behavior.

Acceptance criteria:

- Backend/frontend deploy evidence, commit SHAs, Lambda manifest/runtime, CDK diff/deploy evidence, and quality gates are recorded.
- Production smoke is read-only by default and does not mutate customer report artifacts.
- Safe-fixture mutation smoke records fixture identity, request IDs, artifact version metadata, rollback metadata, cleanup/restore evidence, and privacy denylist results.
- Final audit records residual risks and future requirements.

## Future Requirements

- Rich/WYSIWYG report editor with structured review workflow.
- Compliance-grade WORM audit storage.
- Support ticket/export destination integrations for rollback evidence packages.
- PDF/multilingual delivery.
- Billing, analytics, and broader admin operations expansion.
- Step Functions/SQS or dedicated recovery orchestration if existing Lambda flow becomes insufficient.

## Out of Scope

- Freeform WYSIWYG editing; v2.2 only adds rollback and safe-fixture verification around bounded artifact edits.
- Customer-data production mutation smoke; production mutation is limited to a named non-customer fixture.
- Deleting prior artifact versions during rollback; rollback switches current metadata pointers and preserves version history.
- New AWS resources unless Phase 58 proves existing resources are insufficient.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ROLLBACK-01 | Phase 58 | Planned |
| ROLLBACK-02 | Phase 59 | Planned |
| ROLLBACK-03 | Phase 59 | Planned |
| FIXTURE-01 | Phase 58/59 | Planned |
| UI-09 | Phase 60 | Planned |
| VERIFY-05 | Phase 61 | Planned |
