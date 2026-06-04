# Phase 23: Report Operations List and Detail API - Context

**Gathered:** 2026-06-04
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>

## Phase Boundary

Build the backend admin report operations list/detail API surface for v1.4.

This phase delivers:

- Admin list endpoint for weekly report operation rows.
- Bounded pagination and explicit filters.
- Access-pattern evidence for the admin list.
- Expanded detail response with generation metadata and action eligibility.
- Backend tests for list/detail behavior.

This phase does not implement generation retry, bulk resend, frontend UI, or live verification.

</domain>

<decisions>

## Implementation Decisions

### Endpoint Shape

- Add `GET /admin/reports/ops` for list/filter/page.
- Keep and extend existing `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops` for detail.
- Return metadata only. Do not return raw report HTML/JSON, private S3 object keys, public S3 URLs, presigned URLs, or direct S3 fetch paths.

### Data Access

- Prefer existing DynamoDB table and indexes for Phase 23.
- Use `GSI-ParentId` when parent-specific filters make it useful.
- Use bounded `Scan` only for cross-parent pilot admin list cases.
- Expose `LastEvaluatedKey` as an opaque token and accept it as `next_token`.
- Record the bounded scan decision in verification as the OPS-03 evidence.

### Action Eligibility

- Detail response should include artifact availability, action eligibility, and disabled reasons.
- `email_failed` enables resend.
- `generation_failed` enables generation retry.
- Successful, pending, claimed, or unrelated states disable both actions with clear reasons.

</decisions>

<code_context>

## Existing Code Insights

- `src/stoa/routers/admin.py` already has admin-only report detail and resend endpoints.
- `src/stoa/db/repositories/report_repo.py` has parent/week and parent report query helpers.
- Report records are stored as `PK=REPORT#{report_id}`, `SK=SUMMARY`.
- `tests/test_admin_report_ops.py` already verifies detail privacy and resend behavior.
- Existing pagination patterns use `LastEvaluatedKey` / `ExclusiveStartKey`.

</code_context>

<specifics>

## Specific Ideas

- Add list/detail response models in `admin.py`.
- Add token encode/decode helpers in `report_repo.py` or `admin.py`; repository-level token helpers are preferable because they are DynamoDB-specific.
- Add tests directly in `tests/test_admin_report_ops.py` and `tests/test_parent_children.py` for repository access.

</specifics>

<deferred>

## Deferred Ideas

- CDK-managed status/week GSI unless Phase 23 proves scan is unsafe for current pilot usage.
- Bulk resend.
- Generation retry.
- Frontend report operations page.

</deferred>
