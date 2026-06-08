# Next Three Milestones

**Updated:** 2026-06-08
**Mode:** product functionality first

## v3.4 Learning Expansion Foundation

Goal: prepare Phase 2 learning expansion without jumping directly into a broad curriculum rollout.

Planned phases:

- Phase 104: Multi-Subject Taxonomy And Prompt Contract.
- Phase 105: Backend Subject/Topic Support And Student Learning Profile Seeds.
- Phase 106: Student And Parent Learning Profile UI.
- Phase 107: v3.4 Functional Release Gate And Expansion Audit.

Scope:

- Add a durable subject/topic taxonomy for math-first expansion into physics, German, and English.
- Start student learning profile fields from existing questions, feedback, weak-topic data, and teacher escalation signals.
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

## v3.6 Payment Provider Readiness

Goal: prepare Stripe/TWINT integration after manual subscription operations are proven.

Planned phases:

- Phase 112: Payment Provider Contract And Billing Data Model.
- Phase 113: Backend Payment Intent/Webhook Readiness.
- Phase 114: Parent Payment Readiness UI And Admin Billing Signals.
- Phase 115: v3.6 Functional Release Gate And Provider Integration Audit.

Scope:

- Define provider boundaries, subscription mapping, webhook state machine, billing metadata, and operational failure states.
- Start with readiness and sandbox-safe flows before any real charge path.
- Keep production charging disabled unless explicitly approved with provider credentials and safe test customers.
