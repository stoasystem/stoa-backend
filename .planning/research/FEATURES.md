# v5.19 Research: Features

## Table Stakes

- Native app shell with role-aware navigation for student and parent users.
- Environment configuration for development, staging/production-like API targets, Cognito, notification project IDs, and no-demo-fallback behavior.
- Registration/sign-in, email verification, resend-code, session restore, refresh, and sign-out flows that match Cognito and existing backend policy.
- Mobile-safe account state surfaces for verification, billing, entitlements, child binding, usage/quota, provider failures, and support explanations.
- Student core journeys: dashboard, curriculum/practice read, question submission, quota/paid-access state, teacher-help state, notifications, and learning history summary.
- Parent core journeys: dashboard, child summary, child history, child report, account operations, billing/subscription state, and support-facing explanations.
- Push token registration and revocation through backend notification APIs.
- Notification list, read/archive actions, foreground/background handling, and authenticated deep links into the relevant student or parent screen.
- Offline/read-through cache for selected read-only summaries with explicit freshness, privacy, and sign-out clearing rules.
- Mobile localization, text-fit, accessibility, and common viewport checks.
- Internal build evidence, screenshots, tests, known limitations, and provider/app-store prerequisite documentation.

## Differentiators

- Push deep links land on useful authenticated screens, not only the app home screen.
- Parent and student users can reopen key summary screens with stale/read-through data when temporarily offline.
- Mobile account-state messaging remains support-safe and specific instead of returning generic forbidden or unauthorized screens.
- Release evidence ties mobile readiness to the existing v5.18 observability and provider-state work, so deployment decisions are evidence-based.

## Anti-Features

- Live App Store or Play Store launch without a separate release approval.
- Full offline mutation for question submission, teacher help, quota-consuming actions, billing changes, or account operations.
- Native payments or in-app purchases unless explicitly scoped and legally reviewed.
- Caching raw prompts, answers, tutoring transcripts, generated reports, Cognito token material, provider payloads, or billing-provider payloads.
- Admin/tutor mobile workflows unless needed for a smoke-only support path.
- A second mobile-only entitlement, billing, or notification model that bypasses existing backend contracts.

## Scope Boundary

v5.19 should implement enough native client behavior to prove the real app path: auth, core student/parent use, push, offline-read, and release evidence. It should not expand the product domain beyond already-defined backend and web contracts.
