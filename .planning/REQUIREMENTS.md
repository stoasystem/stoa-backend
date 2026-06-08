# Requirements: v3.5 Realtime And Teacher Assistance Foundation

**Milestone:** v3.5
**Status:** Active
**Created:** 2026-06-08

## Goal

Prepare realtime and teacher-assistance expansion without jumping directly into a broad WebSocket rollout or automatic exercise generation. This milestone adds a bounded notification event model, backend event surfaces, teacher assistance summary seeds, tutor/admin UI surfaces, and lightweight functional verification.

## Requirements

### NOTIFY-01 Realtime Notification And Teacher Assistance Contract

Implementers have a precise notification event contract, delivery boundary, and teacher assistance seed contract before backend changes.

Acceptance criteria:

- Contract defines notification events for teacher request, teacher takeover, teacher reply, moderation update, subscription request update, and learning profile update.
- Contract defines delivery states: `created`, `read`, `archived`, and `failed`.
- Contract defines recipient roles, target ids, event payload shape, retention expectations, and UI display rules.
- Contract defines teacher assistance summary seed inputs from question content, AI response, teacher replies, topic/profile metadata, and conversation context.
- Contract explicitly keeps full WebSocket streaming and automatic exercise generation out of v3.5 unless later promoted.

### NOTIFY-02 Backend Notification Events And Teacher Summary Seeds

Backend records and exposes notification events and teacher assistance seed summaries.

Acceptance criteria:

- Backend creates notification events for selected existing workflows without changing their core behavior.
- Users can list and mark their notification events read/archived.
- Tutor/admin surfaces can request teacher assistance summary seeds for visible questions/sessions.
- Backend stores minimal summary seed metadata and avoids generating full autonomous exercise content.
- Focused tests cover event creation/list/read/archive, recipient filtering, and summary seed generation from existing data.

### UI-20 Tutor/Admin Notification And Summary UI

Frontend exposes notification and teacher-assistance foundations.

Acceptance criteria:

- Student/parent/tutor/admin shell can display notification counts and event list states where relevant.
- Tutor question/session UI shows a teacher assistance summary seed panel.
- Admin UI shows selected operational notification events for moderation/subscription workflows.
- UI handles empty, loading, error, read, archived, and unavailable summary states.
- Targeted browser verification confirms the workflow is usable.

### VERIFY-18 v3.5 Functional Release Gate And Expansion Audit

v3.5 closes with lightweight functional evidence and updated Phase 2 gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to notifications and teacher assistance pass.
- Deploy/build evidence and commit SHAs are recorded if code ships in this milestone.
- Gap audit marks notification foundation and teacher assistance seeds as active/closed and records residual full WebSocket/exercise-generation scope.
- Final audit lists remaining Phase 2 product expansions: Stripe/TWINT, full curriculum rollout, full personalization, production WebSocket rollout, mobile/multilingual polish, and support integrations.

## Future Requirements

- Full WebSocket realtime delivery.
- Automatic exercise generation and richer AI teacher tools.
- Stripe/TWINT payment-provider integration.
- Full multi-subject curriculum content and exercises.
- Student memory/personalization beyond profile and summary seeds.
- Mobile responsive polish and full multilingual rollout.

## Out of Scope

- Full WebSocket infrastructure or streaming UX.
- Push notifications, native mobile notifications, or email notification digests.
- Automatic exercise generation.
- Payment-provider implementation.
- Extensive security/compliance testing beyond functional role gating and data sanity checks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| NOTIFY-01 | Phase 108 | Complete |
| NOTIFY-02 | Phase 109 | Planned |
| UI-20 | Phase 110 | Planned |
| VERIFY-18 | Phase 111 | Planned |
