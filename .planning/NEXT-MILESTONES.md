# Next Three Milestones

**Updated:** 2026-06-09
**Mode:** product functionality first

## v3.7 AI Teacher Tools And Exercise Generation

Goal: turn the v3.5 teacher-assistance seeds and v3.4 learning profile foundations into usable teacher tools for automatic summaries, suggested focus, draft explanations, and bounded exercise generation.

Planned phases:

- Phase 116: AI Teacher Tools Contract And Generation Model.
- Phase 117: Backend Teacher Summary And Exercise Draft APIs.
- Phase 118: Tutor AI Tools And Exercise Draft UI.
- Phase 119: v3.7 Functional Release Gate And AI Tools Audit.

Scope:

- Generate session summaries, misconception summaries, suggested teaching focus, draft follow-up explanations, and practice exercise drafts from existing learning and conversation context.
- Keep all AI-generated replies and exercises in teacher/admin-reviewed draft states.
- Reuse existing AI/Bedrock, subject taxonomy, learning profile seed, notification, and tutor UI foundations where possible.
- Keep automatic student assignment, full curriculum exercise banks, and autonomous tutoring decisions out of scope.

## v3.8 Payment Provider Readiness

Goal: prepare Stripe/TWINT integration after manual subscription operations are proven.

Planned phases:

- Phase 120: Payment Provider Contract And Billing Data Model.
- Phase 121: Backend Payment Intent/Webhook Readiness.
- Phase 122: Parent Payment Readiness UI And Admin Billing Signals.
- Phase 123: v3.8 Functional Release Gate And Provider Integration Audit.

Scope:

- Define provider boundaries, subscription mapping, webhook state machine, billing metadata, and operational failure states.
- Start with readiness and sandbox-safe flows before any real charge path.
- Keep production charging disabled unless explicitly approved with provider credentials and safe test customers.

## v3.9 Mobile And Multilingual Polish Foundation

Goal: reduce the largest remaining usability gaps after learning, realtime, AI teacher tools, and payment readiness foundations.

Planned phases:

- Phase 124: Mobile And Multilingual Polish Contract.
- Phase 125: Responsive Navigation And Core Flow Polish.
- Phase 126: Translation Coverage And Language Preference UI.
- Phase 127: v3.9 Functional Release Gate And Polish Audit.

Scope:

- Improve mobile ergonomics for parent/student/tutor core flows without redesigning the product.
- Expand frontend translation coverage around high-traffic workflows.
- Keep native mobile apps and full localization operations out of scope unless promoted by a later milestone.
