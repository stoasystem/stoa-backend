# Requirements: v3.2 Content Moderation And Internal Operations

**Milestone:** v3.2
**Status:** Active
**Created:** 2026-06-08

## Goal

Close the remaining MVP admin workflow gap from `stoa_docs`: content moderation for reported or abnormal learning content. This milestone prioritizes product functionality for internal development: user-facing report actions, admin moderation queue/detail/actions, and operational visibility. Security testing stays limited to basic role gating and privacy sanity checks.

## Requirements

### MOD-01 Content Moderation Contract And Data Model Readiness

Implementers have a precise moderation case contract, data model, and API plan before backend changes.

Acceptance criteria:

- Contract defines reportable surfaces: student question content, AI answer, teacher reply, and optional freeform user note.
- Contract defines moderation case status lifecycle: `open`, `in_review`, `actioned`, `dismissed`, and `closed`.
- Contract defines reason/severity fields, reporter identity, subject identifiers, assigned admin, timestamps, resolution notes, and audit history.
- Contract confirms whether the existing DynamoDB single-table patterns support queue/list/detail access without new infrastructure.
- Functional verification plan focuses on happy path, role gating, status transitions, pagination/filtering, and UI usability.

### MOD-02 Backend Moderation Reporting And Admin APIs

Backend supports creating moderation cases and managing them from admin APIs.

Acceptance criteria:

- Students and teachers/tutors can create a bounded report against an existing question or teacher reply they are allowed to view.
- Admins can list moderation cases with filters for status, severity, reason, reporter role, assignee, and date.
- Admins can open a case detail with the relevant question context and existing AI/teacher response summaries.
- Admins can assign, update status, add resolution notes, and close/dismiss/action a case.
- Focused tests cover case creation, admin list/detail/actions, invalid target handling, and non-admin rejection.

### UI-17 Moderation Reporting And Admin Queue UI

Frontend exposes practical moderation workflows for internal operations.

Acceptance criteria:

- Student question/detail UI offers a report action with reason, severity, and optional note.
- Teacher/tutor question detail UI offers a report action for abnormal student content or answer context.
- Admin UI includes moderation queue, filters, case detail, assignment/status actions, and resolution note controls.
- UI handles empty, loading, error, submitted, actioned, dismissed, and closed states.
- Targeted browser verification confirms the internal workflow is usable without requiring production customer mutations.

### VERIFY-15 v3.2 Functional Release Gate And STOA Docs Alignment

v3.2 closes with lightweight functional evidence and updated `stoa_docs` gap tracking.

Acceptance criteria:

- Backend and frontend focused quality gates relevant to moderation pass.
- Deploy/build evidence and commit SHAs are recorded if code ships in this milestone.
- `STOA_DOCS_FEATURE_GAP_AUDIT.md` marks content moderation as closed or accurately records residuals.
- Final audit lists remaining Phase 2 product expansions: payments, multi-subject, student memory, AI teacher tools, realtime notifications, mobile/multilingual polish, and support integrations.

## Future Requirements

- Stripe/TWINT subscription payments.
- Parent-facing subscription management beyond manual admin tier updates.
- Broad multi-subject rollout for physics, German, and English.
- Student memory/personalization.
- AI teacher assistance tools such as summaries and exercise generation.
- WebSocket realtime notifications.
- Mobile responsive polish and full multilingual rollout.
- Real user email verification policy change if product/legal requires it.

## Out of Scope

- Payment-provider integration.
- Broad Phase 2 curriculum expansion.
- Compliance-grade moderation/legal workflows.
- New AWS infrastructure unless Phase 96 proves the existing table/access patterns cannot support the MVP.
- Extensive security audit beyond basic authorization/privacy checks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| MOD-01 | Phase 96 | Complete |
| MOD-02 | Phase 97 | Complete |
| UI-17 | Phase 98 | Planned |
| VERIFY-15 | Phase 99 | Planned |
