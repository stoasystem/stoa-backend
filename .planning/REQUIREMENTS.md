# Requirements: Report Operations Admin UI / Bulk Recovery

**Defined:** 2026-06-04
**Core Value:** Parents can trust that parent portal views reflect authorized real student data from the backend, not hidden demo fallbacks.

## v1.4 Requirements

### Admin Report Operations API

- [x] **OPS-01**: Admin can list weekly report operation rows with report status, email status, generation error, delivery error, last operation, and updated timestamps.
- [x] **OPS-02**: Admin report list supports bounded pagination and explicit filters for status, week start, parent ID, and student ID where the backend access pattern supports them.
- [x] **OPS-03**: Backend either proves the current DynamoDB access pattern is safe for the pilot admin list or adds a CDK-managed index before broad list usage.
- [x] **OPS-04**: Admin can fetch one report operation detail with artifact availability metadata, generation metadata, delivery metadata, and operation audit metadata.
- [x] **OPS-05**: Report operation detail exposes action eligibility and disabled reasons for retry/resend actions.

### Generation Recovery

- [x] **GEN-01**: Admin can retry one `generation_failed` report for a specific parent, student, and week.
- [x] **GEN-02**: Generation retry preserves the canonical report ID and `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}` artifact keys.
- [x] **GEN-03**: Generation retry refuses successful, pending, generated, `email_sent`, and `email_failed` reports unless a future explicit regenerate feature is designed.
- [x] **GEN-04**: Generation retry records operator, action, attempt time, completion/failure time, result, and error class/message.

### Delivery Recovery

- [x] **DEL-01**: Admin can bulk resend selected `email_failed` reports with a backend-enforced maximum batch size.
- [x] **DEL-02**: Bulk resend validates each selected report independently and returns per-report success, refused, not-found, or failed results.
- [x] **DEL-03**: Bulk resend uses existing private HTML artifacts through backend-mediated S3 reads and never returns raw report content to the client.
- [x] **DEL-04**: Bulk resend records per-report operator, action, attempt time, completion/failure time, result, and error class/message.

### Admin UI

- [x] **UI-01**: Admin can open a report operations page from the admin navigation.
- [x] **UI-02**: Admin report operations UI shows list filters, loading state, empty state, error state, paginated results, and status badges.
- [x] **UI-03**: Admin can inspect one report row in a detail view or panel without leaving the report operations workflow.
- [x] **UI-04**: Admin can trigger allowed retry/resend actions from the UI and see per-action or per-item results.
- [x] **UI-05**: Admin report operations UI does not use silent demo fallback for operational data or recovery actions.

### Privacy, Authorization, and Verification

- [x] **SEC-01**: All report operations list, detail, retry, and bulk resend endpoints are admin-only.
- [x] **SEC-02**: Report operations API and UI never expose raw report HTML/JSON, public S3 URLs, presigned URLs, or direct frontend S3 fetch paths.
- [x] **VER-01**: Backend tests cover list/detail access, status filtering, generation retry, bulk resend, per-item results, audit fields, and non-admin rejection.
- [x] **VER-02**: Frontend tests cover report operations navigation, filters/states, detail inspection, action eligibility, bulk selection, and result rendering.
- [x] **VER-03**: Live verification records deployed API state, frontend route behavior, and at least one safe recovery smoke path.

## Future Requirements

Deferred to a future milestone.

### Operations Expansion

- **FUT-01**: Admin can run incident-wide asynchronous recovery jobs for large report failure events.
- **FUT-02**: Admin can view a separate immutable report operation audit log beyond fields stored on the report record.
- **FUT-03**: Admin can regenerate already successful reports as an explicit content-refresh workflow.
- **FUT-04**: Report operations integrate with support tickets or incident notes.

### Report Product Expansion

- **FUT-05**: Admin can manage PDF report generation.
- **FUT-06**: Admin can manage multilingual report delivery.
- **FUT-07**: Report access can be gated by billing/subscription state.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Public or presigned S3 report URLs | v1.3 established backend-mediated private artifact access. |
| Raw report HTML/JSON preview in admin UI | Recovery needs metadata/actions, not content exposure. |
| Step Functions redrive orchestration | Current report workflow is Lambda/API based; adding Step Functions is not needed unless bounded synchronous recovery proves insufficient. |
| Large incident-wide bulk recovery | v1.4 targets selected, capped recovery; large asynchronous jobs are future scope. |
| Editing generated report content | This milestone is operations recovery, not report authoring. |
| PDF or multilingual report output | Product expansion remains separate from operations recovery. |
| Billing-gated report recovery | Billing access control is not required to make admin recovery usable. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| OPS-01 | Phase 23 | Complete |
| OPS-02 | Phase 23 | Complete |
| OPS-03 | Phase 23 | Complete |
| OPS-04 | Phase 23 | Complete |
| OPS-05 | Phase 23 | Complete |
| GEN-01 | Phase 24 | Complete |
| GEN-02 | Phase 24 | Complete |
| GEN-03 | Phase 24 | Complete |
| GEN-04 | Phase 24 | Complete |
| DEL-01 | Phase 25 | Complete |
| DEL-02 | Phase 25 | Complete |
| DEL-03 | Phase 25 | Complete |
| DEL-04 | Phase 25 | Complete |
| UI-01 | Phase 26 | Complete |
| UI-02 | Phase 26 | Complete |
| UI-03 | Phase 26 | Complete |
| UI-04 | Phase 26 | Complete |
| UI-05 | Phase 26 | Complete |
| SEC-01 | Phase 27 | Complete |
| SEC-02 | Phase 27 | Complete |
| VER-01 | Phase 27 | Complete |
| VER-02 | Phase 27 | Complete |
| VER-03 | Phase 27 | Complete |

**Coverage:**

- v1.4 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-06-04*
*Last updated: 2026-06-04 after Phase 27 completion*
