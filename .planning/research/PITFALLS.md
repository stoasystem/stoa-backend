# Project Research - Pitfalls

**Milestone:** v1.4 Report Operations Admin UI / Bulk Recovery
**Date:** 2026-06-04

## Pitfalls and Prevention

### Duplicate sends from retries

Risk:

- AWS Lambda and manual recovery flows can be retried or repeated.
- A bulk resend can send duplicate emails if the same selected item is submitted twice or if a network retry repeats a successful request.

Prevention:

- Validate current status immediately before action.
- Record `last_operation`, `last_operation_by`, `last_operation_result`, and timestamps.
- Consider operation-in-progress fields or conditional updates for retry/resend claims.
- Return per-item result states so the UI does not blindly re-run a completed batch.

### Retrying generation through the wrong path

Risk:

- The scheduled job's claim path cannot simply reclaim an existing `generation_failed` report, because the conditional put has already created a record.

Prevention:

- Build a dedicated generation retry service that validates the existing failed record and transitions it intentionally.
- Preserve the same report ID and canonical artifact keys.
- Refuse generated/email-sent/email-failed reports unless a future explicit regenerate feature is designed.

### Admin list data access becoming an unbounded table scan

Risk:

- The current single-table model has parent/week report query support, but not an obvious admin status/week query for all reports.

Prevention:

- Phase 23 must inspect current CDK/DynamoDB indexes before implementation.
- Use strict `limit` and pagination.
- If bounded scan is not acceptable, add a CDK-managed GSI before building a broad admin list.

### Long-running bulk operations in API Gateway/Lambda

Risk:

- Large resend batches can exceed API/Lambda execution budgets or SES rate constraints.

Prevention:

- Enforce a small max batch size for v1.4.
- Process sequentially or with constrained concurrency.
- Return per-item results.
- Defer large incident-wide recovery to a future queued/asynchronous job if needed.

### Privacy regression through admin UI

Risk:

- Admins may accidentally receive raw report HTML/JSON, public S3 URLs, or presigned URLs.

Prevention:

- Keep detail responses metadata-only.
- Reuse backend-mediated private S3 reads only inside resend/retry services.
- Add tests asserting no response contains raw HTML, `https://s3`, `presignedUrl`, or public URL fields.

### Frontend demo fallback hiding operational failures

Risk:

- Admin recovery UI could mask API failures with demo data, undermining the point of operational tooling.

Prevention:

- No silent demo fallback for report operations.
- Show explicit loading, empty, error, refused, and partial-success states.
- Invalidate/refetch React Query caches after actions.

### Missing audit detail

Risk:

- A recovery action succeeds or fails but support cannot tell who ran it, when, or why it failed.

Prevention:

- Every action writes actor, action, attempt time, completion/failure time, result, and error class/message.
- Bulk response mirrors the persisted audit outcome per item.

### Overbuilding orchestration

Risk:

- Adding Step Functions or queues before proving the simple recovery path insufficient increases infrastructure and IAM surface.

Prevention:

- Keep v1.4 on existing API/Lambda/service structure.
- Revisit asynchronous orchestration only when batch size, timeout, or incident recovery requirements exceed the bounded synchronous path.
