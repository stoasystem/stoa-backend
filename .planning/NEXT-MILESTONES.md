# Next Three Milestones

**Updated:** 2026-06-14 after selecting v5.0
**Mode:** product functionality first

## v4.8 Support Provider Expansion And CRM Automation

**Status:** Completed backend release gate 2026-06-12
**Roadmap:** `.planning/milestones/v4.8-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.8-REQUIREMENTS.md`

Goal: expand the v4.5 internal support queue into approved provider-backed support operations and controlled CRM/customer messaging.

Closed scope:

- Added adapter readiness, provider delivery workers, bounded retry, provider ticket sync, support SLA analytics, and template-gated support messaging.
- Final provider activation state is `provider-ready`; real external provider and CRM/customer writes remain gated on approved provider selection, credentials, destination policy, templates, and rollout approval.

## v4.9 Production Notification And Native Delivery Rollout

**Status:** Completed backend release gate 2026-06-14
**Roadmap:** `.planning/milestones/v4.9-ROADMAP.md`
**Requirements:** `.planning/milestones/v4.9-REQUIREMENTS.md`

Goal: complete live notification delivery beyond backend readiness.

Closed scope:

- Added live WebSocket/API Gateway readiness, provider-backed email/push delivery, push token lifecycle records, frontend/native notification handoff, and release evidence.
- Final rollout state is `deferred` pending live deployment, provider activation, frontend implementation, native app work, and explicit rollout approval.

## v5.0 Native Mobile And Full Localization Governance

**Status:** Active planning
**Roadmap:** `.planning/milestones/v5.0-ROADMAP.md`
**Requirements:** `.planning/milestones/v5.0-REQUIREMENTS.md`

Goal: move beyond selected responsive frontend/localization polish into native/mobile rollout readiness and complete localization governance.

Candidate phases:

- Phase 171: Native Mobile And Localization Governance Contract.
- Phase 172: Mobile App API Readiness And Client Handoff.
- Phase 173: Native Notification Token And Offline State Handoff.
- Phase 174: Localization Governance Translation QA And Locale Coverage.
- Phase 175: v5.0 Native Mobile Localization Release Gate And Handoff.

Scope:

- Build mobile API/client handoff, native notification/offline contracts, translation governance, copy QA, locale coverage, and client-ready release evidence.
- Keep canonical API values stable while improving localized display behavior.
- Avoid full native app binary implementation inside this backend workspace unless a dedicated native workspace is selected.

## Candidate v5.1 Product Expansion Or Final External Activation

**Status:** Candidate after v5.0 or when external prerequisites unblock

Potential scope:

- Final live payment activation operations once external provider prerequisites are ready.
- Real external support provider and CRM/customer transport activation after approved provider prerequisites are ready.
- Rich curriculum editor UI and production content migration.
- Long-term adaptive sequencing, autonomous tutoring, and warehouse-backed analytics.

## Candidate v5.2 Curriculum Product Expansion

**Status:** Candidate after v5.1 if external activation remains blocked

Potential scope:

- Rich curriculum editor UI.
- Production content migration.
- Automatic assignment of reviewed/generated exercises.
- Deeper adaptive sequencing and analytics.
