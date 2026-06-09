# Next Three Milestones

**Updated:** 2026-06-09 after completing v3.7
**Mode:** product functionality first

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

## v4.0 Production Notifications And Support Integration Readiness

Goal: close the remaining notification and operations handoff gaps after local WebSocket and in-product notification foundations are stable.

Planned phases:

- Phase 128: Production Notification Delivery Contract.
- Phase 129: API Gateway WebSocket And Push/Email Delivery Readiness.
- Phase 130: Support Evidence Destination Contract And Admin Signals.
- Phase 131: v4.0 Functional Release Gate And Operations Integration Audit.

Scope:

- Prepare production WebSocket route wiring and live-smoke evidence requirements.
- Define push/native/email notification delivery boundaries and opt-in/out behavior.
- Define support-ticket/evidence handoff readiness without assuming connector credentials.
- Keep real production notification senders or support mutations behind explicit credential and safety approval.
