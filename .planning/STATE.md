---
gsd_state_version: 1.0
milestone: v4.6
milestone_name: Rich Curriculum Authoring And Analytics Foundation
status: in_progress
last_updated: "2026-06-12T09:46:05.000Z"
last_activity: 2026-06-12
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 4
  completed_plans: 2
  percent: 50
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-12)

**Core value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.
**Current focus:** v4.6 rich curriculum authoring and analytics foundation.

## Current Position

Phase: 154 - Learning Analytics And Content Quality Signals
Plan: 154-01
Status: Ready for Phase 154 planning
Last activity: 2026-06-12 — Phase 153 admin curriculum authoring MVP completed

## Accumulated Context

### Decisions

- v3.3 completed manual subscription operations for parent requests and admin tier processing.
- v3.9 completed the local Stripe-first payment provider MVP: checkout session creation, provider billing status, signed webhook lifecycle, parent payment UX, and admin billing visibility.
- v4.0 through v4.3 completed adaptive learning, notification readiness, frontend mobile polish, and visual localization foundations.
- The next active feature gap is support evidence integrations and operations handoff.
- v4.5 should prioritize a controlled support destination contract, credential readiness, one approved delivery path, and operator-visible handoff status.
- Phase 145 owns production checkout/webhook rollout plus TWINT-capable Stripe provider primitives and livemode gating.
- Phase 146 owns refunds, invoices, dunning, Swiss tax/accounting handoff, and TWINT lifecycle behavior inside the same Stripe billing model.
- Phase 144 completed the live payment rollout contract and confirmed no real customer charge was enabled.
- Phase 145 completed fail-closed readiness states, provider lookup rows, TWINT eligibility metadata, and redacted parent/admin billing readiness surfaces.
- Phase 146 completed invoice/receipt metadata, non-mutating refund readiness, dunning projections, Swiss accounting handoff export, and TWINT lifecycle propagation.
- Phase 147 completed the v4.4 release gate and confirmed real customer charging remains deferred until external approval and live provider setup.
- Real customer charging remains gated on approved provider credentials and explicit production rollout approval.
- v4.5 research confirmed existing support handoff packages already preserve metadata-only manual preview/copy/download behavior and refuse unapproved external writes.
- Phase 148 owns the support destination contract, credential/config readiness, payload rules, attachment policy, and refusal behavior before delivery implementation.
- Phase 148 completed the support destination contract and selected `internal_queue` as the first approved Phase 149 destination path with `none_required` third-party credentials and `SUPPORT_INTERNAL_QUEUE_APPROVED=true` as the rollout approval gate.
- Phase 149 completed the fail-closed `internal_queue` delivery path, admin-only sibling delivery endpoint, provider-neutral delivery lifecycle records, idempotency independent of package UUIDs, and refused-record handling for contract-defined unapproved destinations.
- Phase 150 completed admin-only support handoff delivery queue/detail visibility with recent feed rows, pre-feed read-through coverage, bounded audit timelines, complete lifecycle state visibility, and read-only retry eligibility.
- Phase 151 completed the v4.5 local backend release gate with provider-failure lifecycle coverage, focused/full backend gates, Ruff, imported frontend support handoff evidence from Phases 68/69/70, and updated remaining-feature documentation.
- v4.6 should build on the v3.8 curriculum catalog/exercise-bank foundation and v4.0 adaptive-learning signals to add internal authoring, QA lifecycle, and actionable content analytics.
- Phase 152 completed the curriculum authoring contract, stable-public-ID versus immutable-version model, separate lifecycle state machines, publish manifest rules, validation requirements, role boundaries, and legacy readiness handoff for Phase 153.
- Phase 153 completed a dedicated curriculum operations repository/service/admin route layer for draft, review, approve, request changes, publish, rollback, archive, preview, audit, and worklist behavior while preserving published-only student reads.

### Pending Todos

- Plan Phase 154: learning analytics and content quality signals.

### Blockers/Concerns

- Live payment rollout requires approved production provider credentials before any real charging path is enabled.
- Stripe-backed TWINT rollout may still require provider account capability checks, CHF eligibility verification, or external merchant onboarding state before live enablement.
- Refund execution remains intentionally non-mutating; operators receive provider handoff metadata rather than direct refund mutation.
- Swiss tax/accounting fields are provider-managed when provider data is unavailable locally.
- Broad security/compliance testing should stay proportionate to touched payment paths during this internal development stage.
- Support destination delivery remains fail-closed unless `SUPPORT_INTERNAL_QUEUE_APPROVED=true`; third-party destinations remain refused until separate secret-backed provider phases approve them.
- v4.5 does not enable live third-party support-system writes; approved provider adapters, retry workers, two-way sync, SLA analytics, and broader CRM/customer messaging remain future work.

## Operator Next Steps

- Begin Phase 154 analytics planning against the version/public-ID fields added by Phase 153.
