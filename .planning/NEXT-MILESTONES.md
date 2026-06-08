# Next Three Milestones

**Updated:** 2026-06-08
**Mode:** product functionality first

## v3.3 Subscription Operations MVP

Goal: make the manual MVP subscription model usable before integrating Stripe/TWINT.

Planned phases:

- Phase 100: Subscription Operations Contract And Entitlement Model.
- Phase 101: Backend Subscription Request And Admin Tier APIs.
- Phase 102: Parent Subscription Management UI And Admin Queue.
- Phase 103: v3.3 Functional Release Gate And Billing Readiness.

Scope:

- Preserve manual billing while giving parents a clear plan view, request/upgrade/cancel intent, and admin processing workflow.
- Record subscription source, requested tier, current tier, effective date, internal note, and status.
- Keep actual payment-provider integration out of scope until v3.4+.

## v3.4 Learning Expansion Foundation

Goal: prepare Phase 2 learning expansion without jumping directly into a broad curriculum rollout.

Planned phases:

- Phase 104: Multi-Subject Taxonomy And Prompt Contract.
- Phase 105: Backend Subject/Topic Support And Student Learning Profile Seeds.
- Phase 106: Student/Parent Learning Profile UI Polish.
- Phase 107: v3.4 Functional Release Gate And Expansion Audit.

Scope:

- Add a durable subject/topic taxonomy for math-first expansion into physics, German, and English.
- Start student learning profile fields from existing questions, feedback, and weak-topic data.
- Prepare AI teacher assistance and personalization hooks without shipping full autonomous exercise generation yet.

## v3.5 Realtime And Teacher Assistance Foundation

Goal: prepare the next teacher-support expansion after moderation, subscriptions, and learning-profile foundations.

Planned phases:

- Phase 108: Realtime Notification And Teacher Assistance Contract.
- Phase 109: Backend Notification Events And Teacher Summary Seeds.
- Phase 110: Tutor/Admin Notification And Summary UI.
- Phase 111: v3.5 Functional Release Gate And Expansion Audit.

Scope:

- Add a bounded notification event model before any broad WebSocket rollout.
- Prepare teacher assistance summaries from existing question/conversation context.
- Keep automatic exercise generation, full personalization, mobile polish, and multilingual rollout out of scope unless a later milestone explicitly promotes them.
