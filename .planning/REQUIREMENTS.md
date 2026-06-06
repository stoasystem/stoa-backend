# Requirements: v2.3 Release Evidence Automation And Fixture Lifecycle

**Milestone:** v2.3
**Status:** Active
**Created:** 2026-06-06

## Goal

Operators can produce repeatable, redacted release evidence bundles and manage the named non-customer safe fixture lifecycle without expanding production mutation scope.

## Requirements

### EVIDENCE-AUTO-01 Release Evidence Contract And Redaction Model

Implementers have a precise release evidence contract before adding evidence automation code.

Acceptance criteria:

- Contract defines required bundle fields for backend deploy, frontend deploy, Lambda build manifest, Lambda runtime state, CDK diff/deploy, admin-only API checks, production browser smoke, request IDs, commit SHAs, timestamps, and privacy denylist results.
- Contract distinguishes required evidence from optional notes and known-skipped checks.
- Redaction model forbids secrets, auth tokens, passwords, S3 keys, presigned URLs, raw report JSON/HTML, raw artifact payloads, and customer-identifying fixture data in committed evidence.
- Evidence bundle can represent read-only production smoke and explicitly approved fixture-only mutation smoke.

### EVIDENCE-AUTO-02 Backend Release Evidence Collection Tooling

Operators can collect and validate release evidence through repeatable backend-side tooling.

Acceptance criteria:

- Tooling validates the Phase 62 evidence schema and reports missing required release gate fields.
- Tooling collects or accepts deploy run IDs, commit SHAs, Lambda runtime state, CDK diff classification, API request IDs, and smoke summaries.
- Tooling writes redacted evidence output suitable for `.planning` release gate docs.
- Tooling fails closed when private marker denylist checks fail.

### FIXTURE-02 Safe Fixture Lifecycle And Inventory

Operators can inspect and maintain the named non-customer safe fixture lifecycle without customer-impacting mutation.

Acceptance criteria:

- Fixture lifecycle defines identity, ownership, allowed mutation modes, cleanup/restore evidence, retention policy, and emergency disable steps.
- Fixture inventory output is sanitized and omits private S3 keys, presigned URLs, raw JSON/HTML, and raw artifact payloads.
- Production mutation tooling refuses to run without an explicit approved fixture name and explicit mutation mode.
- Fixture status can be used during release gates to prove safe fixture readiness or justify skipped mutation smoke.

### UI-10 Admin Release Evidence And Fixture Status UI

Admin report operations UI exposes sanitized release evidence and fixture status.

Acceptance criteria:

- UI exposes admin-only release evidence and safe-fixture status views without performing mutation.
- UI renders sanitized deploy metadata, fixture status, request IDs, commit SHAs, validation failures, and privacy denylist results.
- UI does not render secrets, S3 keys, presigned URLs, raw report JSON/HTML, or raw artifact payloads.
- Playwright covers admin-only gating, happy path, error states, and privacy denylist.

### VERIFY-06 v2.3 Release Gate And Milestone Audit

v2.3 closes with release and live verification evidence for release evidence automation and fixture lifecycle controls.

Acceptance criteria:

- Backend/frontend deploy evidence, commit SHAs, Lambda manifest/runtime, CDK diff/deploy evidence, local quality gates, API request IDs, and browser smoke results are recorded.
- Production smoke is read-only by default and does not mutate customer report artifacts.
- Any fixture mutation verification uses only the approved named non-customer fixture and records cleanup/restore evidence.
- Final audit records residual risks and future requirements.

## Future Requirements

- Compliance-grade WORM audit storage.
- Support ticket/export destination integrations for release and rollback evidence.
- Rich/WYSIWYG report editor.
- PDF/multilingual delivery.
- Billing, analytics, and broader admin operations expansion.
- Step Functions/SQS or dedicated recovery orchestration if existing Lambda flow becomes insufficient.

## Out of Scope

- Customer-data production mutation smoke.
- New AWS resources unless Phase 62 proves current resources are insufficient.
- Replacing GitHub Actions, CDK, CloudFront, or Cognito operational ownership.
- Long-term immutable audit storage; v2.3 can define compatibility requirements but should not implement WORM storage.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EVIDENCE-AUTO-01 | Phase 62 | Complete |
| EVIDENCE-AUTO-02 | Phase 63 | Complete |
| FIXTURE-02 | Phase 62/63 | Complete |
| UI-10 | Phase 64 | Not started |
| VERIFY-06 | Phase 65 | Not started |
