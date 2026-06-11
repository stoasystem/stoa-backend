# Roadmap: STOA Backend

## Completed Milestones

- [x] **v1.0 Parent Portal Real Data Integration** - Shipped 2026-06-02.
- [x] **v1.1 Weekly Report Automation** - Shipped 2026-06-02.
- [x] **v1.2 S3 Report Artifact Infrastructure** - Shipped 2026-06-04.
- [x] **v1.3 Report Artifact Security & Operations Hardening** - Shipped 2026-06-04.
- [x] **v1.4 Report Operations Admin UI / Bulk Recovery** - Shipped 2026-06-04.
- [x] **v1.5 Report Recovery Production Rollout & Live Smoke** - Shipped 2026-06-04.
- [x] **v1.6 Report Recovery Operations Hardening** - Shipped 2026-06-05.
- [x] **v1.7 Recovery Evidence Export & Admin Credential Operations** - Shipped 2026-06-05.
- [x] **v1.8 Incident Generation Retry Jobs** - Shipped 2026-06-05.
- [x] **v1.9 Recovery Resume And Support Evidence Packages** - Shipped 2026-06-05.
- [x] **v2.0 Controlled Report Editing MVP** - Shipped 2026-06-05.
- [x] **v2.1 Report Artifact Versioning And Safe Edit Preview** - Shipped 2026-06-06.
- [x] **v2.2 Report Artifact Rollback And Safe Fixture Verification** - Shipped 2026-06-06.
- [x] **v2.3 Release Evidence Automation And Fixture Lifecycle** - Shipped 2026-06-06.
- [x] **v2.4 Support Evidence Export Destinations And Ticket Handoff** - Shipped 2026-06-07; production verification closed by v2.5.
- [x] **v2.5 Production Support Handoff Verification Closeout** - Shipped 2026-06-07.
- [x] **v2.6 Audit Retention And Immutable Evidence Readiness** - Shipped 2026-06-07.
- [x] **v2.7 Immutable Audit Storage And Legal Hold Foundation** - Shipped 2026-06-07.
- [x] **v2.8 CDK-Managed Immutable Evidence Storage Deployment** - Shipped 2026-06-07.
- [x] **v2.9 Retention Governance And Legal Hold Operations** - Complete local-only 2026-06-07; production verification closed by v3.0.
- [x] **v3.0 STOA Docs Gap Closeout And Account Intake Hardening** - Shipped 2026-06-08.
- [x] **v3.1 Teacher Reply Quality And SLA Operations** - Shipped 2026-06-08.
- [x] **v3.2 Content Moderation And Internal Operations** - Shipped 2026-06-08.
- [x] **v3.3 Subscription Operations MVP** - Completed local release gate 2026-06-08.
- [x] **v3.4 Learning Expansion Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.5 Realtime And Teacher Assistance Foundation** - Completed local release gate 2026-06-08.
- [x] **v3.6 Full WebSocket Realtime Notifications** - Completed local release gate 2026-06-09.
- [x] **v3.7 AI Teacher Tools And Exercise Generation** - Completed local release gate 2026-06-09.
- [x] **v3.8 Full Curriculum Rollout** - Completed local release gate 2026-06-09.
- [x] **v3.9 Payment Provider Integration MVP** - Completed local release gate 2026-06-09.
- [x] **v4.0 Adaptive Learning Memory And Assignment** - Completed local backend release gate 2026-06-10.

## v4.1 Mobile And Multilingual Polish Foundation

**v4.1 Mobile And Multilingual Polish Foundation** - Planned.

Goal: prepare mobile-friendly and multilingual polish through backend contracts, durable locale preferences, language-safe response metadata, and release evidence that separates completed backend work from deferred frontend/native UI implementation.

## Phases

**Phase Numbering:**

- Integer phases continue across milestones.
- Decimal phases are reserved for urgent insertions and marked INSERTED.

- [x] **Phase 132: Mobile And Multilingual Contract Foundation** - Define backend/client boundaries, mobile UAT criteria, supported locale policy, and the v4.1 gap audit. (completed 2026-06-11)
- [x] **Phase 133: Locale Preference APIs** - Implement durable locale preference storage, profile exposure, normalization, fallback, and focused tests. (completed 2026-06-11)
- [x] **Phase 134: Role Route Contract Polish** - Apply language metadata and mobile-friendly response checks to selected student, parent, tutor, and admin flows. (completed 2026-06-11)
- [ ] **Phase 135: Release Gate And Documentation** - Verify regression coverage, update docs/gap audit, and record deferred frontend/native scope.

## Phase Details

### Phase 132: Mobile And Multilingual Contract Foundation

**Goal**: Define v4.1 backend/client scope, mobile-readiness criteria, supported-locale policy, route audit targets, and gap-audit updates before code changes.
**Depends on**: v4.1 research
**Requirements**: MOBILE-01
**Success Criteria** (what must be TRUE):

  1. Mobile-critical student, parent, tutor, and admin flows are identified with backend route contract implications.
  2. Supported locale and fallback policy is documented for the backend foundation.
  3. Backend versus frontend/native ownership is explicit, including what this repository cannot visually verify.
  4. The feature gap audit is updated from v4.0 personalization language to v4.1 mobile/multilingual scope.

**Plans**: 1/1 plans complete

Plans:

- [x] 132-01: Define mobile and multilingual backend contract.

### Phase 133: Locale Preference APIs

**Goal**: Add durable locale preference support with shared normalization/fallback and authenticated profile/preference API exposure.
**Depends on**: Phase 132
**Requirements**: I18N-01
**Success Criteria** (what must be TRUE):

  1. Authenticated profile/preference responses expose effective locale for existing and new users.
  2. Supported locale updates persist durably on backend profile/user data.
  3. Missing, malformed, unsupported, and supported locale behavior is deterministic and tested.
  4. Existing authorization and clients without locale inputs remain compatible.

**Plans**: 1/1 plans complete

Plans:

- [x] 133-01: Implement locale preference backend APIs.

### Phase 134: Role Route Contract Polish

**Goal**: Apply language-safe metadata and mobile-friendly response contract checks to selected role-critical backend routes.
**Depends on**: Phase 133
**Requirements**: I18N-02
**Success Criteria** (what must be TRUE):

  1. Selected student, parent, tutor, and admin responses expose locale/language metadata where display content depends on language.
  2. Canonical IDs, statuses, enum values, timestamps, permissions, and storage keys remain stable across locale preferences.
  3. Mobile-sensitive list/detail or summary contracts are bounded and documented where route payloads need polish.
  4. Focused tests cover role visibility, canonical-value stability, and metadata behavior across locales.

**Plans**: 1/1 plans complete

Plans:

- [x] 134-01: Polish role route contracts for locale and mobile readiness.

### Phase 135: Release Gate And Documentation

**Goal**: Close v4.1 with verification evidence, updated planning artifacts, and an honest deferred-scope record for frontend/native mobile and visual localization work.
**Depends on**: Phase 134
**Requirements**: VERIFY-24
**Success Criteria** (what must be TRUE):

  1. Focused backend tests and relevant static checks pass or isolate documented pre-existing failures.
  2. Requirements, roadmap, feature gap audit, and release evidence reflect completed v4.1 backend work.
  3. Deferred frontend/native mobile and visual localization tasks are explicitly listed.
  4. Final milestone audit ties shipped behavior back to MOBILE-01, I18N-01, I18N-02, and VERIFY-24.

**Plans**: TBD

Plans:

- [ ] 135-01: Verify v4.1 and update release documentation.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 132 Mobile And Multilingual Contract Foundation | v4.1 | 1/1 | Complete   | 2026-06-11 |
| 133 Locale Preference APIs | v4.1 | 1/1 | Complete   | 2026-06-11 |
| 134 Role Route Contract Polish | v4.1 | 1/1 | Complete   | 2026-06-11 |
| 135 Release Gate And Documentation | v4.1 | 0/1 | Not started | - |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOBILE-01 | Phase 132 | Complete |
| I18N-01 | Phase 133 | Complete |
| I18N-02 | Phase 134 | Complete |
| VERIFY-24 | Phase 135 | Planned |

---
*Last updated: 2026-06-11 after completing Phase 134*
