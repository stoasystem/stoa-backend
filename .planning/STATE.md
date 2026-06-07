---
gsd_state_version: 1.0
milestone: v2.9
milestone_name: Retention Governance And Legal Hold Operations
status: planning
last_updated: "2026-06-07T19:27:21+02:00"
last_activity: 2026-06-07
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 4
  completed_plans: 1
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-07)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v2.9 retention governance and legal-hold operations.

## Current Position

Phase: 83 Retention Policy And Legal Hold Governance Readiness
Plan: 83-01 Retention Policy And Legal Hold Governance Readiness
Status: Planned.
Last activity: 2026-06-07 — planned v2.9 Retention Governance And Legal Hold Operations.

## Accumulated Context

### Decisions

- v1.8 shipped async generation retry jobs.
- v1.9 shipped recovery subset resume and support-safe evidence packages.
- v2.0 shipped controlled metadata-only report editing.
- Raw report artifact editing remains higher risk than metadata editing and must start with contract/CDK readiness before implementation.
- v2.1 must preserve backend-mediated artifact access and must not expose S3 keys, presigned URLs, raw JSON, or raw unreviewed HTML to frontend.
- Phase 54 proved existing reports bucket, API Lambda S3 object permissions, and DynamoDB table grants are sufficient for versioned artifact editing under `weekly-reports/*`; no CDK change is required for Phase 55.
- Phase 55 added admin-only artifact edit preview/read/apply APIs with versioned artifact writes, stale-source rejection, rollback metadata, and redacted report audit evidence.
- Phase 56 added selected-report admin artifact edit preview/apply UI, kept preview separate from mutation, and verified frontend privacy denylist coverage with lint, build, and Playwright.
- Phase 57 deployed backend/frontend v2.1, confirmed Lambda runtime state and CDK code-asset-only drift, and passed production read-only API/browser smoke with artifact edit bundle markers and no private marker exposure.
- v2.2 added artifact rollback and a named non-customer safe-fixture mutation verification path before broader artifact editing use.
- Phase 58 proved existing reports bucket, API Lambda S3 object permissions, and DynamoDB grants are sufficient for rollback and fixture harness work; no CDK change is required for Phase 59.
- Phase 59 added admin-only artifact rollback preview/read/apply APIs, rollback action eligibility, redacted rollback audit evidence, stale-source rejection, and an explicit safe-fixture smoke harness.
- Phase 60 added selected-report artifact rollback preview/apply UI, required operator reasons, rendered only sanitized version metadata, and verified privacy denylist coverage with lint, build, and Playwright.
- Phase 61 confirmed backend/frontend deploys, Lambda runtime state, CDK diff, production read-only API/browser smoke, safe-fixture harness default refusal, and approved safe-fixture mutation/cleanup.
- Phase 61 found and fixed a selected-report lookup bug where artifact edit draft child entities could be returned from `GSI-ParentId` instead of the report summary row.
- v2.3 should turn manually assembled release evidence into a repeatable redacted evidence workflow before expanding any production mutation capability.
- Phase 62 starts with release evidence schema, redaction rules, fixture lifecycle, and CDK readiness.
- v2.4 should turn support-safe recovery/release/rollback evidence into manual ticket handoff packages before any direct third-party integration.
- Phase 66 starts with support handoff schema, destination refusal policy, privacy model, audit requirements, and CDK readiness.
- Phase 66 completed with a metadata-only support handoff package contract, manual preview/copy/download destination policy, explicit `external_write` refusal, privacy denylist, redacted audit metadata rules, and a no-new-CDK-resource readiness decision.
- Phase 67 completed admin-only backend support handoff package generation with metadata-only recovery/release/fixture/operator-note sections, direct external write refusal, append-only support handoff audit rows, privacy validation, and focused backend tests.
- Phase 68 completed frontend admin support handoff controls on `/admin/report-operations` with preview/copy/download/refusal states and focused Playwright coverage.
- Phase 69 completed local release gate evidence and milestone audit; production deployment and read-only live smoke are deferred because v2.4 commits were not deployed from this thread.
- v2.4 milestone closeout archived audit, roadmap, requirements, and phase records with production live verification deferred.
- v2.5 should close only the deferred v2.4 production deployment/read-only verification gap without adding product scope.
- Phase 70 closed the deferred v2.4 production verification gap with backend/frontend deploy evidence, Lambda runtime metadata, CDK diff classification, production API smoke, production browser smoke, and final audit.
- v2.5 milestone closeout archived audit, roadmap, requirements, and phase records.
- v2.6 should start with audit retention and immutability readiness before claiming WORM/compliance-grade storage.
- Phase 71 starts with retention contract, immutability boundary, privacy model, and CDK readiness.
- Phase 71 completed with metadata-only retention manifest/status contracts, a no-new-CDK-resource readiness decision, and explicit future-scope boundaries for compliance-grade WORM storage.
- Phase 72 added admin-only metadata retention status and manifest APIs with canonical digests, privacy validation, refusal behavior, and redacted append-only audit metadata.
- Phase 73 added admin audit retention controls on `/admin/report-operations` with status, manifest, copy/download, digest preview, refusal reasons, and e2e privacy assertions.
- Phase 74 deployed and production-verified v2.6 with backend/frontend Actions evidence, Lambda runtime metadata, CDK diff, API smoke, browser smoke, and final audit.
- v2.6 milestone closeout archived audit, roadmap, requirements, and phase records.
- v2.7 starts with immutable audit storage and legal hold foundation because v2.6 explicitly deferred compliance-grade WORM/Object Lock storage, legal hold administration, retention policy administration, and full manifest object persistence.
- Phase 75 must define immutable storage, legal hold, privacy, and CDK readiness contracts before any backend production write path is implemented.
- Phase 75 completed with metadata-only immutable storage and legal hold contracts, CDK readiness evidence, and a decision that Phase 76 must fail closed while CDK-managed immutable storage configuration is absent.
- Phase 76 added admin-only immutable evidence status/persist and legal hold status/apply APIs, with immutable persistence refusing `not_configured` until CDK-managed storage settings exist.
- Phase 77 added frontend admin immutable evidence and legal hold controls in stoa-frontend commit c1e2676.
- Phase 78 deployed and production-verified v2.7 with backend/frontend Actions evidence, Lambda runtime metadata, CDK diff, API smoke, browser smoke, and final audit.
- Integration audit blockers were fixed in backend commit 2e2d942: configured immutable persistence now writes a create-only metadata object before marking the manifest reference persisted, and legal-hold writes now use compare-and-set semantics.
- v2.7 shipped as a metadata-only, admin-only, fail-closed immutable evidence/legal hold foundation; compliance-grade WORM/Object Lock storage remains future scope.
- v2.8 starts with CDK-managed immutable evidence storage deployment because v2.7 left WORM/Object Lock resource deployment and full immutable manifest object persistence as residual gaps.
- Phase 79 must define CDK design, deploy readiness, backend configuration contract, and live verification boundary before Phase 80 creates infrastructure.
- Phase 79 selected a dedicated retained, versioned, Object Lock-enabled immutable evidence S3 bucket in `StorageStack`, API Lambda env vars, and scoped `audit-retention/*` S3 permissions for Phase 80.
- Phase 80 deployed the dedicated retained, versioned, Object Lock-enabled immutable evidence bucket through stoa-infra commit `c3d0d60` and workflow run `27098074719`.
- Phase 80 verified live Object Lock default retention in GOVERNANCE mode for 365 days, public access block, AES256 encryption, server access logging, API-only immutable env vars, and API IAM limited to `s3:GetObject`/`s3:PutObject` on the approved prefix.
- Phase 81 added env-driven immutable readiness coverage and duplicate/reference-exists refusal coverage.
- Phase 81 production read-only smoke verified `stoa-api` immutable storage public status is `ready`, `cdk_managed=true`, `resource_configured=true`, and `prefix_configured=true` without exposing private storage identifiers.
- Phase 82 persisted one approved metadata-only release evidence immutable manifest in production and verified API, DynamoDB, S3 Object Lock headers, and browser smoke without customer report artifact mutation.
- v2.9 starts with retention governance and legal-hold operations because v2.8 left the 365-day GOVERNANCE retention period and operational legal-hold procedure pending formal approval.
- Phase 83 must define the governance contract, approval packet, runbook specification, and privacy-safe verification boundary before backend/UI governance metadata is implemented.

### Pending Todos

- Complete Phase 83 by finalizing governance contract, approval packet, legal-hold runbook spec, and Phase 84 entry criteria.

### Blockers/Concerns

- Production smoke must remain read-only unless a named non-customer safe fixture and cleanup path are documented.
- Artifact apply must not overwrite prior report artifact versions in place; Phase 55 writes new versioned objects before metadata pointer update.
- Frontend must never receive S3 keys, presigned URLs, raw report JSON, or raw unreviewed HTML.
- Rollback must preserve prior artifact versions and switch only validated current metadata pointers.
- The synthetic safe fixture remains in production as a named non-customer verification target.
- Release evidence automation must fail closed on private marker denylist hits.
- Phase 62 finalized the release evidence bundle schema, redaction model, safe-fixture lifecycle, and CDK readiness decision.
- Phase 63 added backend release evidence validation, safe-fixture inventory, mutation refusal checks, CLI tooling, admin validate/status endpoints, and focused tests.
- Phase 64 added admin report operations release evidence validation and safe-fixture status UI controls in the frontend without adding mutation actions.
- Phase 65 completed with deploy evidence, Lambda runtime state, CDK diff classification, local quality gates, production read-only API/browser smoke, safe-fixture refusal checks, and final milestone audit.
- Direct external ticket writes must remain refused until an approved connector or secret-backed credential path exists.
- Compliance-grade WORM audit storage must not be claimed without deployed CDK-managed immutable storage evidence.
- Immutable evidence objects must remain metadata-only and must not include raw report artifacts, S3 keys, presigned URLs, raw JSON/HTML, auth tokens, cookies, passwords, or AWS secrets.
- The 365-day GOVERNANCE retention period and operational legal-hold procedure still need formal compliance/legal approval before broad compliance claims.
- v2.9 must not provide legal advice or fabricate approval; it can only create and verify the approval workflow and record actual approval metadata if supplied through an approved path.

## Operator Next Steps

- Execute Phase 83 plan and complete retention governance/legal-hold readiness documentation.
