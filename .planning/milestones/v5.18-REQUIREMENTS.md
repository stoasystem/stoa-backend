# Requirements: v5.18 Warehouse BI Observability And Product Analytics Activation

**Milestone:** v5.18
**Status:** Active
**Created:** 2026-07-05
**Prior milestone:** v5.17 External Provider Activation Smoke And Release Operations

## Purpose

Activate support-safe product analytics and observability after usage semantics, provider states, and release-smoke readiness are explicit. v5.18 should give operators aggregate dashboards, repeatable export contracts, and alert routing without exposing raw student content, provider payloads, secrets, or high-cardinality private identifiers.

## Requirements

### BI-01 Analytics Reality Audit And Taxonomy

Acceptance criteria:

- Existing analytics/readiness surfaces are mapped across usage/quota, billing/provider readiness, curriculum analytics/migration, teacher help, notifications, support handoff, core smoke, and external activation smoke.
- A shared taxonomy distinguishes `live_ready`, `read_only_verifiable`, `safe_fixture_verifiable`, `locally_ready`, `blocked`, `failed`, and `unknown` states.
- Privacy boundaries are documented before any export/dashboard activation.
- Missing evidence needed for dashboards, exports, or alerts is routed to later v5.18 phases.

### BI-02 Warehouse Export Job Activation

Acceptance criteria:

- Aggregate warehouse export/readiness outputs are repeatable, idempotent, bounded, and support-safe.
- Export schemas include product surface, period, aggregate counts, blocker/status dimensions, generated timestamp, and privacy metadata.
- Backfill, retry, partial-failure, and stale-data behavior is documented and test-covered.
- Exports exclude raw prompts, answers, provider payloads, secrets, Cognito token material, report artifact content, and private S3 keys.

### BI-03 Operator Analytics Dashboards

Acceptance criteria:

- Admin/operator dashboard APIs summarize usage/quota, billing/provider readiness, curriculum/migration/editor health, teacher-help/support load, notification delivery, support-provider lifecycle, and release-smoke outcomes.
- Dashboards expose blocker categories, support actions, stale/partial data flags, and provider-state dimensions.
- Dashboard responses are aggregate/support-safe and avoid raw student content or raw provider payloads.
- Focused tests prove empty states, blocked states, and support-safe redaction behavior.

### BI-04 APM And Alert Routing

Acceptance criteria:

- Core flows emit or expose low-cardinality status/error dimensions suitable for APM and alerts.
- Alert routing separates product regressions from external-provider blockers and read-only/local-only states.
- Alert payloads avoid high-cardinality private identifiers and raw content.
- Operator runbooks define severity, ownership, escalation, suppression, retry/backfill, and known provider-blocked states.

### VERIFY-52 BI Observability Release Gate

Acceptance criteria:

- Focused backend checks pass for export/dashboard/alert contracts touched by v5.18.
- BI activation evidence records live-ready, read-only, local-only, blocked, and failed limitations honestly.
- Roadmap, requirements, state, milestone snapshots, runbooks, and next milestone recommendation are updated.
- Remaining BI/provider/APM/native limitations are explicit.

## Out of Scope

- Raw learning analytics warehouse containing prompts, answers, chat messages, report artifacts, or provider payloads.
- Live third-party BI SaaS integration requiring new credentials unless explicitly approved.
- Customer-facing analytics features.
- Native/mobile implementation; planned for v5.19.
- Production mutation outside approved fixture/mode gates.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BI-01 | Phase 262 | Planned |
| BI-02 | Phase 263 | Planned |
| BI-03 | Phase 264 | Planned |
| BI-04 | Phase 265 | Planned |
| VERIFY-52 | Phase 266 | Planned |
