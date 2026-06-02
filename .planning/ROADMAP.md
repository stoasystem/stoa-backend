# Roadmap: v1.0 Parent Portal Real Data Integration

## Overview

This milestone moves the parent portal from mock/demo-backed flows to authorized real backend data. Work starts by proving the CDK, DynamoDB, Cognito, and configuration assumptions, then delivers secure `/parents/me/...` backend routes, real child summary/history/report data, frontend service alignment without silent demo fallback, and focused verification. Scope intentionally excludes automatic weekly report generation, EventBridge targets, SES workflows, PDF generation, and broad frontend redesign.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Infrastructure and Contract Grounding** - Confirm CDK-backed resources, parent-child access patterns, environment configuration, and identity mapping before backend route work. (completed 2026-06-02)
- [x] **Phase 2: Parent Child List and Access Rules** - Let logged-in parents list only linked children while blocking normal parent flows for the wrong roles. (completed 2026-06-02)
- [x] **Phase 3: Child Summary, History, and Report Data** - Deliver child-specific parent routes with real aggregation, ownership checks, and stable available/missing states. (completed 2026-06-02)
- [ ] **Phase 4: Frontend Parent Portal Integration** - Align parent services and pages to `/parents/me/...` backend responses without silent demo fallback.
- [ ] **Phase 5: Verification and Test Data** - Prove backend, client, route-contract, and real-data behaviors with focused tests and documented test accounts.

## Phase Details

### Phase 1: Infrastructure and Contract Grounding

**Goal**: Implementer has confirmed CDK-backed resource assumptions and parent identity/lookup contracts so backend work can proceed without invented infrastructure.
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, DATA-04, DATA-05
**Success Criteria** (what must be TRUE):

  1. Implementer can point to CDK definitions for the DynamoDB table, GSIs, Cognito groups/app clients, Lambda environment variables, report bucket, and report permissions used by the parent portal.
  2. Implementer can state whether parent-child lookup uses an existing index, an accepted MVP scan, or a CDK-backed GSI change.
  3. Backend resource names and URLs used by this milestone are known to come from CDK-provided environment variables, not hard-coded assumptions.
  4. Parent ownership lookup has a documented canonical identifier path for Cognito `sub` versus local user ID compatibility.

**Plans**: 1/1 complete

### Phase 2: Parent Child List and Access Rules

**Goal**: Logged-in parents can list only their own linked children through `/parents/me/children`, while normal parent flows reject students, teachers/tutors, and admins.
**Depends on**: Phase 1
**Requirements**: PARENT-01, PARENT-02, PARENT-08, AUTHZ-01, AUTHZ-03, AUTHZ-04, AUTHZ-05
**Success Criteria** (what must be TRUE):

  1. Parent can call `GET /parents/me/children` and receive only children linked to that parent from real DynamoDB records.
  2. Parent with no linked children receives `{ "items": [] }` from `GET /parents/me/children`.
  3. Student, teacher, tutor, and admin users cannot use normal `/parents/me/...` parent flows outside explicit authorized routes.
  4. Existing `/parents/{parent_id}/...` endpoints remain compatible unless implementation evidence documents a necessary change.

**Plans**: 2/2 complete

### Phase 3: Child Summary, History, and Report Data

**Goal**: Linked parents can open child-specific summary, history, and report routes backed by real data, stable empty states, and ownership checks.
**Depends on**: Phase 2
**Requirements**: PARENT-03, PARENT-04, PARENT-05, PARENT-06, PARENT-07, AUTHZ-02, AUTHZ-06, DATA-01, DATA-02, DATA-03
**Success Criteria** (what must be TRUE):

  1. Linked parent can open a child summary with stable real-data aggregation and no fabricated mock values.
  2. Linked parent can open child history as newest-first real learning events, with `{ "items": [] }` when no events exist.
  3. Linked parent can open current/latest and week-specific report lookups that return `status: "available"` or `status: "missing"` without fabricated content.
  4. Cross-parent child summary, history, and report requests are denied before reading or returning child data.
  5. Child, summary, history, and report responses match the milestone frontend-friendly data shapes.

**Plans**: 3/3 complete

### Phase 4: Frontend Parent Portal Integration

**Goal**: Parent portal services and pages consume `/parents/me/...` real backend responses with explicit empty and error states instead of silent demo fallback.
**Depends on**: Phase 3
**Requirements**: FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, FRONT-06
**Success Criteria** (what must be TRUE):

  1. Parent frontend services call `/parents/me/...` routes for normal logged-in parent flows.
  2. Parent dashboard renders backend child list responses and the no-child state without demo fallback.
  3. Child summary/detail and learning history views render backend data with explicit empty and error states.
  4. Child report view renders both available-report and missing-report backend states.
  5. Parent-critical pages surface backend failures instead of hiding them behind `withDemoFallback`.

**Plans**: TBD
**UI hint**: yes

### Phase 5: Verification and Test Data

**Goal**: Milestone behavior is covered by focused backend/client tests and documented test data so the real parent flow can be verified.
**Depends on**: Phase 4
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09, TEST-10
**Success Criteria** (what must be TRUE):

  1. Backend tests prove parent ownership, cross-parent denial, non-parent rejection, empty child list, and missing report behavior.
  2. Client-side or service tests prove real-response rendering, no-child state, missing-report state, and `/parents/me/...` service path alignment.
  3. Test data or documentation identifies one parent account, one linked student account, and enough activity to verify summary/history.
  4. Full milestone verification demonstrates a real parent can log in, see children, open summary/history, and see available/missing report states without mock fallback.

**Plans**: TBD

## Coverage

| Phase | Requirement Count | Requirements |
|-------|-------------------|--------------|
| 1. Infrastructure and Contract Grounding | 5 | INFRA-01, INFRA-02, INFRA-03, DATA-04, DATA-05 |
| 2. Parent Child List and Access Rules | 7 | PARENT-01, PARENT-02, PARENT-08, AUTHZ-01, AUTHZ-03, AUTHZ-04, AUTHZ-05 |
| 3. Child Summary, History, and Report Data | 10 | PARENT-03, PARENT-04, PARENT-05, PARENT-06, PARENT-07, AUTHZ-02, AUTHZ-06, DATA-01, DATA-02, DATA-03 |
| 4. Frontend Parent Portal Integration | 6 | FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, FRONT-06 |
| 5. Verification and Test Data | 10 | TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06, TEST-07, TEST-08, TEST-09, TEST-10 |

Mapped: 38/38 v1 requirements.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure and Contract Grounding | 1/1 | Complete | 2026-06-02 |
| 2. Parent Child List and Access Rules | 2/2 | Complete | 2026-06-02 |
| 3. Child Summary, History, and Report Data | 3/3 | Complete | 2026-06-02 |
| 4. Frontend Parent Portal Integration | 0/TBD | Not started | - |
| 5. Verification and Test Data | 0/TBD | Not started | - |
