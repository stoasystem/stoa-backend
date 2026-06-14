# Phase 171 Context: Native Mobile And Localization Governance Contract

## Why This Phase Exists

STOA has backend locale preference foundations, selected responsive frontend polish, and backend notification/native delivery handoff. The remaining `stoa_docs` mobile/localization gap is broader: native mobile rollout readiness, native push/offline handoff, translation management, broad copy QA, RTL/future-locale readiness, and a client release workflow.

v5.0 starts with a contract phase so backend, frontend, native, localization, content, and release responsibilities are explicit before implementation expands across workspaces.

## Current Foundation

- v4.1 added mobile-ready backend route contracts, durable locale preferences, and language-safe response metadata.
- v4.3 added selected frontend mobile responsive polish and English/German locale preference UI in `/Users/zhdeng/stoa-frontend`.
- v4.9 added backend notification delivery readiness, push token lifecycle records, provider-gated email/push delivery, and frontend/native handoff evidence.
- `src/stoa/services/locale_service.py` and `src/stoa/routers/auth.py` contain current backend locale preference behavior.
- `src/stoa/routers/notifications.py`, `src/stoa/services/notification_service.py`, and related tests contain current notification/token behavior.
- `stoa_docs` remaining-feature queue now recommends native mobile and full localization governance.

## Phase Boundary

This phase is planning/contract work. It should define what Phase 172 through Phase 175 implement and what remains outside this backend workspace. It should not attempt to build a complete native app binary.

## Key Files To Inspect

- `src/stoa/services/locale_service.py`
- `src/stoa/routers/auth.py`
- `src/stoa/routers/notifications.py`
- `src/stoa/services/notification_service.py`
- `tests/test_locale_preferences.py`
- `tests/test_notifications.py`
- `.planning/phases/132-mobile-multilingual-contract-and-gap-audit/`
- `.planning/phases/133-locale-preference-backend-support/`
- `.planning/phases/134-language-safe-route-contracts-and-mobile-polish-readiness/`
- `.planning/phases/135-v4-1-mobile-multilingual-release-gate/`
- `.planning/phases/140-frontend-mobile-localization-contract-and-uat-plan/`
- `.planning/phases/141-responsive-core-flow-polish/`
- `.planning/phases/142-visual-localization-language-switching/`
- `.planning/phases/143-v4-3-browser-release-gate-and-localization-audit/`
- `.planning/phases/169-frontend-and-native-notification-ux-handoff/`
- `.planning/phases/170-v4-9-production-notification-release-gate-and-live-smoke/`

## Constraints

- Full native app implementation likely belongs in a dedicated mobile/native workspace.
- Frontend implementation work may belong in `/Users/zhdeng/stoa-frontend`.
- Backend API contracts must preserve canonical values while allowing localized display text.
- Mobile-critical flows should not hide backend failures behind demo fallback.
- Verification should focus on functional contracts, locale correctness, token/offline behavior, and handoff readiness.
