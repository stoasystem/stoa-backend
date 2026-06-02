# Requirements: STOA Parent Portal Real Data Integration

**Defined:** 2026-06-02
**Milestone:** v1.0 Parent Portal Real Data Integration
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## v1 Requirements

### Infrastructure Audit

- [ ] **INFRA-01**: Implementer can confirm DynamoDB table name, GSI names, Cognito groups/app clients, Lambda environment variables, report bucket, and report permissions from `/Users/zhdeng/stoa-infra` CDK before backend changes.
- [ ] **INFRA-02**: Implementer can document whether parent-child lookup is supported by current single-table indexes or whether a CDK-backed GSI change is required.
- [ ] **INFRA-03**: Backend reads resource names and URLs from environment variables injected by CDK, not hard-coded assumptions.

### Parent API

- [ ] **PARENT-01**: Parent can call `GET /parents/me/children` to list linked children from real DynamoDB user/link records.
- [ ] **PARENT-02**: Parent with no linked children receives `{ "items": [] }` from `GET /parents/me/children`.
- [ ] **PARENT-03**: Parent can call `GET /parents/me/children/{child_id}/summary` for a linked child and receive a stable summary response.
- [ ] **PARENT-04**: Parent can call `GET /parents/me/children/{child_id}/history` for a linked child and receive newest-first real learning events with an empty `{ "items": [] }` state when none exist.
- [ ] **PARENT-05**: Parent can call `GET /parents/me/children/{child_id}/report` and receive either `status: "available"` with a real report or `status: "missing"` with `report: null`.
- [ ] **PARENT-06**: Parent can call `GET /parents/me/children/{child_id}/reports/{week}` when the frontend needs a week-specific report lookup.
- [ ] **PARENT-07**: Parent API responses use frontend-friendly child, summary, history, and report shapes matching the milestone data contract.
- [ ] **PARENT-08**: Existing `/parents/{parent_id}/...` endpoints remain compatible unless a specific implementation reason requires changing them.

### Authorization

- [ ] **AUTHZ-01**: Parent can access only children linked to that parent.
- [ ] **AUTHZ-02**: Parent cannot access another parent's child summary, history, or report.
- [ ] **AUTHZ-03**: Student cannot call normal parent endpoints.
- [ ] **AUTHZ-04**: Teacher or tutor cannot call normal parent endpoints unless a separate support/admin workflow is explicitly added.
- [ ] **AUTHZ-05**: Admin access to parent/child data is kept out of normal `/parents/me/...` flows and remains explicit through admin routes.
- [ ] **AUTHZ-06**: Every child-specific parent endpoint verifies ownership before reading or returning child data.

### Data Aggregation

- [ ] **DATA-01**: Child summary aggregates available real data from question, conversation, practice progress, mistake, and report repositories/routes without fabricating mock values.
- [ ] **DATA-02**: Child history combines available real question, conversation, practice, teacher help, and report events into a stable timeline shape.
- [ ] **DATA-03**: Report lookup returns real stored report content when present and never fabricates report content when missing.
- [ ] **DATA-04**: Parent-child identity resolution handles the current Cognito `sub` versus local user ID mismatch risk through a documented canonical identifier or explicit compatibility fallback.
- [ ] **DATA-05**: Child lookup avoids table scans when an existing index supports the access pattern, or documents why scan-based MVP lookup is accepted.

### Frontend Integration

- [ ] **FRONT-01**: Parent frontend services call `/parents/me/...` backend routes for normal logged-in parent flows.
- [ ] **FRONT-02**: Parent dashboard renders backend child list responses without relying on demo fallback.
- [ ] **FRONT-03**: Child summary/detail page renders backend summary and explicit empty/error states.
- [ ] **FRONT-04**: Child learning history page renders backend history and explicit empty/error states.
- [ ] **FRONT-05**: Child report page renders both available-report and missing-report backend states.
- [ ] **FRONT-06**: Parent-critical frontend pages no longer silently hide backend failures with `withDemoFallback`.

### Verification

- [ ] **TEST-01**: Backend tests prove a parent can list only their own children.
- [ ] **TEST-02**: Backend tests prove a parent cannot access another parent's child summary, history, or report.
- [ ] **TEST-03**: Backend tests prove students cannot call parent endpoints.
- [ ] **TEST-04**: Backend tests prove empty child list returns a stable empty response.
- [ ] **TEST-05**: Backend tests prove missing report returns `status: "missing"`, not a 500 or mock content.
- [ ] **TEST-06**: Frontend tests prove parent dashboard renders real API responses.
- [ ] **TEST-07**: Frontend tests prove parent dashboard renders the no-child empty state.
- [ ] **TEST-08**: Frontend tests prove child report page renders missing-report state.
- [ ] **TEST-09**: Frontend tests or service-level assertions prove parent service paths match backend `/parents/me/...` routes.
- [ ] **TEST-10**: Test data or documentation exists for one parent test account, one linked student account, and enough student activity data to verify summary/history.

## v2 Requirements

### Weekly Report Automation

- **REPORT-01**: System can generate weekly report summaries automatically.
- **REPORT-02**: System can use Bedrock to produce report narrative content.
- **REPORT-03**: System can store report artifacts in S3 when needed.
- **REPORT-04**: System can run weekly report generation from an EventBridge schedule target.
- **REPORT-05**: System can send weekly report emails through SES.
- **REPORT-06**: System can monitor and retry report generation/email delivery failures.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic weekly report generation | Separate follow-up milestone focused on report automation. |
| EventBridge schedule target implementation | Not needed to query/display existing or missing reports. |
| SES weekly email sending workflow | Requires report automation and delivery operations beyond this integration milestone. |
| PDF generation | Parent report page only needs stored report data and empty states now. |
| Stripe or billing integration | Unrelated to parent portal data integration. |
| Organization/school portal work | Separate product surface. |
| Live classroom work | Separate product surface. |
| Full admin analytics | Separate admin analytics scope. |
| Broad frontend redesign | Current milestone is contract alignment and real-data behavior. |

## Acceptance Criteria

- A real parent account can log in through the frontend.
- Parent dashboard loads children from backend, not mock data.
- Parent can open child summary backed by real backend aggregation.
- Parent can open child history backed by real backend data.
- Parent report page handles both existing and missing reports correctly.
- Parent-critical frontend pages no longer silently hide backend failures with demo data.
- Backend authorization prevents cross-parent child access.
- Required backend and frontend tests pass.
- Any infrastructure dependency is either confirmed existing in CDK or implemented in CDK.

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | TBD | Pending |
| INFRA-02 | TBD | Pending |
| INFRA-03 | TBD | Pending |
| PARENT-01 | TBD | Pending |
| PARENT-02 | TBD | Pending |
| PARENT-03 | TBD | Pending |
| PARENT-04 | TBD | Pending |
| PARENT-05 | TBD | Pending |
| PARENT-06 | TBD | Pending |
| PARENT-07 | TBD | Pending |
| PARENT-08 | TBD | Pending |
| AUTHZ-01 | TBD | Pending |
| AUTHZ-02 | TBD | Pending |
| AUTHZ-03 | TBD | Pending |
| AUTHZ-04 | TBD | Pending |
| AUTHZ-05 | TBD | Pending |
| AUTHZ-06 | TBD | Pending |
| DATA-01 | TBD | Pending |
| DATA-02 | TBD | Pending |
| DATA-03 | TBD | Pending |
| DATA-04 | TBD | Pending |
| DATA-05 | TBD | Pending |
| FRONT-01 | TBD | Pending |
| FRONT-02 | TBD | Pending |
| FRONT-03 | TBD | Pending |
| FRONT-04 | TBD | Pending |
| FRONT-05 | TBD | Pending |
| FRONT-06 | TBD | Pending |
| TEST-01 | TBD | Pending |
| TEST-02 | TBD | Pending |
| TEST-03 | TBD | Pending |
| TEST-04 | TBD | Pending |
| TEST-05 | TBD | Pending |
| TEST-06 | TBD | Pending |
| TEST-07 | TBD | Pending |
| TEST-08 | TBD | Pending |
| TEST-09 | TBD | Pending |
| TEST-10 | TBD | Pending |

**Coverage:**
- v1 requirements: 38 total
- Mapped to phases: 0
- Unmapped: 38

---
*Requirements defined: 2026-06-02*
*Last updated: 2026-06-02 after starting milestone v1.0*
