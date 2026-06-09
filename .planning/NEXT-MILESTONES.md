# Next Three Milestones

**Updated:** 2026-06-09 after completing v3.8
**Mode:** product functionality first

## v3.9 Payment Provider Readiness

Goal: prepare Stripe/TWINT integration after manual subscription operations are proven.

Planned phases:

- Phase 124: Payment Provider Contract And Billing Data Model.
- Phase 125: Backend Payment Intent/Webhook Readiness.
- Phase 126: Parent Payment Readiness UI And Admin Billing Signals.
- Phase 127: v3.9 Functional Release Gate And Provider Integration Audit.

Scope:

- Define provider boundaries, subscription mapping, webhook state machine, billing metadata, and operational failure states.
- Start with readiness and sandbox-safe flows before any real charge path.
- Keep production charging disabled unless explicitly approved with provider credentials and safe test customers.

## v4.0 Mobile And Multilingual Polish Foundation

Goal: reduce the largest remaining usability gaps after learning, realtime, AI teacher tools, curriculum, and payment readiness foundations.

Planned phases:

- Phase 128: Mobile And Multilingual Polish Contract.
- Phase 129: Responsive Navigation And Core Flow Polish.
- Phase 130: Translation Coverage And Language Preference UI.
- Phase 131: v4.0 Functional Release Gate And Polish Audit.

Scope:

- Improve mobile ergonomics for parent/student/tutor core flows without redesigning the product.
- Expand frontend translation coverage around high-traffic workflows.
- Keep native mobile apps and full localization operations out of scope unless promoted by a later milestone.

## v4.1 Production Notification Delivery Readiness

Goal: turn the local realtime notification stack into production-ready notification delivery and operational evidence.

Planned phases:

- Phase 132: Production Notification Infrastructure Contract.
- Phase 133: API Gateway WebSocket And Delivery Operations Readiness.
- Phase 134: Push/Email Notification Preference And Digest Readiness.
- Phase 135: v4.1 Functional Release Gate And Notification Delivery Audit.

Scope:

- Prepare CDK/API Gateway WebSocket route wiring, deployment evidence, live-smoke expectations, and rollback surfaces.
- Add bounded push/email preference and digest readiness without enabling broad notification spam.
- Keep native apps and final production provider enablement gated on approved credentials and live-smoke targets.
