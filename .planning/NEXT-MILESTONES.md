# Next Three Milestones

**Updated:** 2026-06-08
**Mode:** product functionality first

## v3.6 Full WebSocket Realtime Notifications

Goal: turn the v3.5 notification foundation into full WebSocket realtime delivery.

Planned phases:

- Phase 112: Full WebSocket Transport Contract And Infra Readiness.
- Phase 113: Backend WebSocket Connection And Event Delivery.
- Phase 114: Realtime Notification Client And UX.
- Phase 115: v3.6 Functional Release Gate And Realtime Audit.

Scope:

- Add authenticated WebSocket connection lifecycle, subscription model, event fanout, reconnect, and fallback behavior.
- Preserve the existing notification center as canonical history and fallback.
- Keep native push notifications and email digests out of scope.

## v3.7 Payment Provider Readiness

Goal: prepare Stripe/TWINT integration after manual subscription operations are proven.

Planned phases:

- Phase 116: Payment Provider Contract And Billing Data Model.
- Phase 117: Backend Payment Intent/Webhook Readiness.
- Phase 118: Parent Payment Readiness UI And Admin Billing Signals.
- Phase 119: v3.7 Functional Release Gate And Provider Integration Audit.

Scope:

- Define provider boundaries, subscription mapping, webhook state machine, billing metadata, and operational failure states.
- Start with readiness and sandbox-safe flows before any real charge path.
- Keep production charging disabled unless explicitly approved with provider credentials and safe test customers.

## v3.8 Mobile And Multilingual Polish Foundation

Goal: reduce the largest remaining usability gaps after learning, realtime, and payment readiness foundations.

Planned phases:

- Phase 120: Mobile And Multilingual Polish Contract.
- Phase 121: Responsive Navigation And Core Flow Polish.
- Phase 122: Translation Coverage And Language Preference UI.
- Phase 123: v3.8 Functional Release Gate And Polish Audit.

Scope:

- Improve mobile ergonomics for parent/student/tutor core flows without redesigning the product.
- Expand frontend translation coverage around high-traffic workflows.
- Keep native mobile apps and full localization operations out of scope unless promoted by a later milestone.
