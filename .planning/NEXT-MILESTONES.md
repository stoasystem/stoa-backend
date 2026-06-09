# Next Three Milestones

**Updated:** 2026-06-09 after planning v3.8
**Mode:** product functionality first

## v3.8 Full Curriculum Rollout

Goal: turn the v3.4 subject/topic foundation and v3.7 exercise draft foundation into full curriculum structure and exercise bank coverage for math, physics, German, and English.

Planned phases:

- Phase 120: Full Curriculum Rollout Contract And Content Model.
- Phase 121: Backend Curriculum Catalog And Exercise Bank APIs.
- Phase 122: Student/Parent Curriculum UX And Tutor Signals.
- Phase 123: v3.8 Functional Release Gate And Curriculum Audit.

Scope:

- Define curriculum hierarchy, content states, lesson/exercise fields, and rollout controls.
- Expose backend curriculum catalog and exercise bank APIs while preserving existing practice progress behavior.
- Add student/parent curriculum navigation and tutor/admin curriculum context signals.
- Keep automatic student assignment, full adaptive sequencing, and rich content-authoring workflow out of scope.

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
