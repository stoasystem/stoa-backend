# Phase 150: Operator Queue And Handoff Status Visibility - Research

**Researched:** 2026-06-12 [VERIFIED: current_date]  
**Domain:** FastAPI admin visibility for DynamoDB-backed support handoff delivery lifecycle [VERIFIED: codebase grep]  
**Confidence:** MEDIUM [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html]

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Phase 148 selected `internal_queue` as the first approved support destination path. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Phase 149 implemented `POST /admin/reports/support-handoff-delivery`. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Phase 149 stores provider-neutral delivery summary rows under `SUPPORT_HANDOFF_DELIVERY#{delivery_id}` with `SK=SUMMARY`. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Phase 149 stores append-only delivery audit rows under the same partition with `SK=AUDIT#...`. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Existing package audit rows remain separate under `SUPPORT_HANDOFF#{package_id}`. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- `queued` is the successful `internal_queue` intake state. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- `refused` is used for missing approval, contract-defined unapproved destinations, and package privacy/validation failures. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Unknown destinations remain `422` before evidence reads. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Third-party destinations remain refused until later provider phases. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]

### the agent's Discretion
- Add repository helpers for listing recent support handoff delivery summaries and reading one delivery detail with bounded audit events. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Add admin-only queue/list and detail endpoints under the existing admin report operations router. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Keep returned payloads metadata-only: delivery fields, package ID, destination mode, status, actor, timestamps, correlation ID, retry count, retryable flag, provider object reference, redacted reasons, privacy result, evidence reference IDs, payload digest, and bounded audit event metadata. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- Do not expose raw package sections, raw delivery payload, raw provider payload, raw report artifacts, S3 keys, presigned URLs, cookies, authorization headers, API keys, or OAuth tokens. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- `GET /admin/reports/support-handoff-deliveries` [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
- `GET /admin/reports/support-handoff-deliveries/{delivery_id}` [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]

### Deferred Ideas (OUT OF SCOPE)
- Retry in Phase 150 should be explicit but bounded. If implementation includes a retry endpoint, it must only be available for retryable queued/failed internal queue records and must refuse privacy-failed or unapproved destinations. If safe retry cannot be implemented without broad mutation semantics, expose retry eligibility and defer mutation to a future phase. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SUPPORTINT-03 | Operators can inspect recent support handoff activity and understand whether a package is created, queued, sent, failed, refused, or retried. [VERIFIED: .planning/REQUIREMENTS.md] | `## Summary`, `## Architectural Responsibility Map`, `## Architecture Patterns`, `## Don't Hand-Roll`, `## Common Pitfalls`, `## Validation Architecture`, and `## Security Domain` describe the list/detail API shape, delivery read model, retry visibility stance, privacy guardrails, and tests needed to implement the requirement. [VERIFIED: codebase grep] |
</phase_requirements>

## Summary

Phase 150 should be planned as a read-visibility phase on top of the Phase 149 delivery lifecycle, not as a second delivery-mutation phase. The current backend already persists one delivery summary row per `delivery_id`, appends immutable delivery audit rows in the same partition, exposes only `queued` and `refused` outcomes for `internal_queue`, and keeps `retry_count` fixed at `0` with no update helper for later transitions. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: src/stoa/db/repositories/report_repo.py] [VERIFIED: src/stoa/routers/admin.py]

The main implementation gap is global recency. Phase 149 storage is excellent for point detail reads because `get_support_handoff_delivery_record()` is an exact key lookup and delivery audit rows already fit the existing descending `AUDIT#...` query pattern, but it does not provide a globally ordered "recent deliveries" access path across many `delivery_id` partitions. A bounded table scan would match the existing `/admin/reports/ops` fallback pattern, but scan order is not chronological and DynamoDB applies filter expressions after reading items. The lowest-risk way to get true recent-first admin visibility without a new GSI is to add one read-optimized feed row per delivery in the existing table and query that feed partition with `ScanIndexForward=False`. [VERIFIED: src/stoa/db/repositories/report_repo.py] [VERIFIED: src/stoa/routers/admin.py] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html]

Retry should be visible in Phase 150 but not mutated in Phase 150. Today, a duplicate identical delivery request already reuses the same deterministic `delivery_id`, the current service has no lifecycle transition beyond initial persistence, and the contract says retries must reuse the existing delivery record while privacy-failed and unapproved destinations are not retryable. Exposing a `retry` metadata block now is implementation-ready; adding a retry POST now would require new conditional-update semantics, new audit event shapes, and a clear downstream worker model that the current `internal_queue` implementation does not yet have. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: tests/test_admin_report_ops.py] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]

**Primary recommendation:** Add admin-only list/detail read APIs, back them with a delivery-summary read model plus bounded delivery-audit query, return metadata-only retry eligibility instead of a retry mutation endpoint, and keep all payload shaping behind an explicit allowlist checked by the existing privacy denylist utilities. [VERIFIED: codebase grep] [VERIFIED: src/stoa/services/release_evidence_service.py] [CITED: https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/] [CITED: https://fastapi.tiangolo.com/advanced/testing-dependencies/]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Admin delivery list endpoint with bounded filters and pagination | API / Backend [VERIFIED: codebase grep] | Database / Storage [VERIFIED: codebase grep] | Existing admin list endpoints live in `src/stoa/routers/admin.py`, decode tokens before repo calls, and delegate item retrieval to `report_repo`. [VERIFIED: src/stoa/routers/admin.py] |
| Recent-delivery read model | Database / Storage [VERIFIED: codebase grep] | API / Backend [VERIFIED: codebase grep] | Recency and filterability are determined by DynamoDB key shape; the API should not synthesize global ordering in memory from arbitrary scan pages. [VERIFIED: src/stoa/db/repositories/report_repo.py] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html] |
| Delivery detail summary + bounded audit timeline | Database / Storage [VERIFIED: codebase grep] | API / Backend [VERIFIED: codebase grep] | Detail is naturally a point lookup on `PK=SUPPORT_HANDOFF_DELIVERY#{delivery_id}` plus a descending `AUDIT#` query, matching existing audit patterns. [VERIFIED: src/stoa/db/repositories/report_repo.py] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html] |
| Retry eligibility classification | API / Backend [VERIFIED: codebase grep] | Database / Storage [VERIFIED: codebase grep] | The current service already stores `retryable` and `retry_count`; Phase 150 should expose and explain those fields rather than mutate them. [VERIFIED: src/stoa/services/support_destination_service.py] |
| Privacy-safe response shaping | API / Backend [VERIFIED: codebase grep] | — | The router/service boundary already redacts free text and uses `private_marker_hits()` on structured metadata; response allowlists belong in backend code. [VERIFIED: src/stoa/services/support_handoff_service.py] [VERIFIED: src/stoa/services/release_evidence_service.py] |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | `0.136.3` [VERIFIED: local venv import] | Admin route declaration, dependency-based auth, query/path validation, and testable dependency overrides. [VERIFIED: src/stoa/routers/admin.py] | The existing admin router already uses `Query(...)`, `Depends(require_role("admin"))`, and dependency overrides in tests. [VERIFIED: src/stoa/routers/admin.py] [VERIFIED: tests/test_admin_report_ops.py] [CITED: https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/] [CITED: https://fastapi.tiangolo.com/advanced/testing-dependencies/] |
| Pydantic | `2.13.4` [VERIFIED: local venv import] | Request/response schemas for admin endpoints. [VERIFIED: src/stoa/routers/admin.py] | Phase 150 can stay inside the established `BaseModel` response-model pattern instead of returning untyped dicts. [VERIFIED: src/stoa/routers/admin.py] |
| boto3 DynamoDB Table API | `1.43.16` [VERIFIED: local venv import] | Point reads, descending key queries, conditional writes, and pagination keys on the existing single table. [VERIFIED: src/stoa/db/repositories/report_repo.py] | The repo already uses `get_item`, `put_item`, `query`, and `scan` directly; Phase 150 should extend that layer instead of introducing another storage abstraction. [VERIFIED: src/stoa/db/repositories/report_repo.py] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/scan.html] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | `9.0.3` [VERIFIED: local venv import] | Route-level regression coverage in `tests/test_admin_report_ops.py`. [VERIFIED: tests/test_admin_report_ops.py] | Use for all new list/detail/retry-visibility tests because the existing file already monkeypatches repository seams and settings overrides. [VERIFIED: tests/test_admin_report_ops.py] |
| Ruff | `0.15.14` [VERIFIED: local tool version] | Static lint gate for touched router/repository/test files. [VERIFIED: command run] | Use after adding list/detail helpers and response models. [VERIFIED: command run] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Read-optimized feed row in the existing table [VERIFIED: codebase grep] | Bounded scan over `SUPPORT_HANDOFF_DELIVERY` summary rows [VERIFIED: src/stoa/db/repositories/report_repo.py] | Scan matches the existing `/admin/reports/ops` fallback, but it does not give true recent-first ordering and DynamoDB applies filters after reads. [VERIFIED: src/stoa/routers/admin.py] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html] |
| Retry visibility only in Phase 150 [VERIFIED: src/stoa/services/support_destination_service.py] | Add `POST /admin/reports/support-handoff-deliveries/{delivery_id}/retry` now [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md] | A retry POST would need new conditional updates, lifecycle transitions, and duplicate-click semantics that do not exist in the current `internal_queue` implementation. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] |

**Installation:**
```bash
# No new external packages are recommended for Phase 150.
```

**Version verification:** FastAPI `0.136.3`, Pydantic `2.13.4`, boto3 `1.43.16`, pytest `9.0.3`, and Ruff `0.15.14` were verified from the local environment during research. [VERIFIED: local venv import] [VERIFIED: local tool version]

## Architecture Patterns

### System Architecture Diagram

```text
GET /admin/reports/support-handoff-deliveries
        |
        v
admin.py route
  - require_role("admin")
  - validate limit/status/destination/date/token
  - decode delivery list page token
        |
        v
report_repo.list_support_handoff_delivery_summaries(...)
  - Query PK=SUPPORT_HANDOFF_DELIVERY_FEED
  - SK ordered by created_at
  - ScanIndexForward=False
  - optional FilterExpression for status/destination/package_id
        |
        v
metadata-only summary items
  - retry visibility
  - redacted reasons
  - privacy summary
  - no raw payload

GET /admin/reports/support-handoff-deliveries/{delivery_id}
        |
        v
admin.py route
  - require_role("admin")
  - get summary by exact key
  - decode bounded audit token
        |
        v
report_repo.get_support_handoff_delivery_record(delivery_id)
report_repo.list_support_handoff_delivery_audit_events(delivery_id, ...)
        |
        v
detail response
  - summary fields
  - retry metadata
  - bounded audit events
  - audit_next_token
```

### Recommended Project Structure
```text
src/stoa/
├── routers/admin.py                         # add list/detail route models and handlers [VERIFIED: codebase grep]
├── db/repositories/report_repo.py          # add delivery-feed list helper + delivery-audit list helper + token helpers [VERIFIED: codebase grep]
└── services/support_destination_service.py # add response allowlist/retry eligibility helpers if shared between routes [VERIFIED: codebase grep]

tests/
└── test_admin_report_ops.py                # extend the existing support handoff regression file [VERIFIED: codebase grep]
```

### Pattern 1: Add A Read-Optimized Delivery Feed Row
**What:** Keep the existing per-delivery `SUMMARY` row and append-only `AUDIT#...` rows, but also persist one feed row keyed for recent-first listing, for example `PK=SUPPORT_HANDOFF_DELIVERY_FEED`, `SK=SUMMARY#{created_at}#{delivery_id}`. Update that feed row whenever the delivery summary changes so list results show current status/retry metadata. [VERIFIED: src/stoa/db/repositories/report_repo.py] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html]

**When to use:** Use this for the global `/support-handoff-deliveries` list because the current `delivery_id`-scoped partitioning is good for detail reads but not for recent-first cross-delivery listing. [VERIFIED: src/stoa/db/repositories/report_repo.py]

**Example:**
```python
# Source: existing SUMMARY/AUDIT row conventions in src/stoa/db/repositories/report_repo.py
def list_support_handoff_delivery_summaries(*, limit: int, last_key: dict | None, status: str | None):
    kwargs = {
        "KeyConditionExpression": Key("PK").eq("SUPPORT_HANDOFF_DELIVERY_FEED")
        & Key("SK").begins_with("SUMMARY#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if status:
        kwargs["FilterExpression"] = Attr("status").eq(status)
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return get_table().query(**kwargs)
```

### Pattern 2: Mirror Existing Admin List/Detail Token Handling
**What:** Follow the same route shape used by `GET /admin/reports/ops` and the existing audit endpoints: decode the token before repo calls, raise `HTTPException(400, "Invalid pagination token")` on failure, pass `limit`/filters explicitly, and return a typed response model with `count` and `next_token`. [VERIFIED: src/stoa/routers/admin.py] [CITED: https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/]

**When to use:** Use this for both the delivery list page token and the nested audit page token in the detail route. Add dedicated token scopes rather than broadening the existing report-audit validator. [VERIFIED: src/stoa/db/repositories/report_repo.py]

**Example:**
```python
# Source: src/stoa/routers/admin.py list_report_operations() and list_report_audit_events()
@router.get("/reports/support-handoff-deliveries")
async def list_support_handoff_deliveries(
    limit: int = Query(default=50, ge=1, le=100),
    next_token: str | None = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    try:
        last_key = report_repo.decode_support_handoff_delivery_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
    result = report_repo.list_support_handoff_delivery_summaries(limit=limit, last_key=last_key)
    return {"items": result.get("Items", []), "count": len(result.get("Items", []))}
```

### Pattern 3: Expose Retry Status, Not Retry Mutation
**What:** Keep Phase 150 read-only from a delivery-lifecycle perspective and return a small `retry` block such as `{enabled, reason, count}` derived from `status`, `retryable`, `retry_count`, destination mode, and privacy/refusal reasons. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]

**When to use:** Use this in both list and detail responses because operators need to know whether a handoff can be retried, but the current service has no safe mutation path beyond deterministic duplicate request reuse. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: tests/test_admin_report_ops.py]

**Example:**
```python
# Source: current action-eligibility style in src/stoa/routers/admin.py::_report_action_eligibility
def retry_status(record: dict[str, object]) -> dict[str, object]:
    if record.get("destination_mode") != "internal_queue":
        return {"enabled": False, "reason": "destination is not approved for retry", "count": record.get("retry_count", 0)}
    if not record.get("retryable"):
        return {"enabled": False, "reason": "delivery state is not retryable", "count": record.get("retry_count", 0)}
    return {"enabled": True, "reason": None, "count": record.get("retry_count", 0)}
```

### Anti-Patterns to Avoid
- **Using package audit rows as the delivery queue API:** package generation and delivery lifecycle are separate in the Phase 148 contract and in the Phase 149 storage shape. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md] [VERIFIED: src/stoa/db/repositories/report_repo.py]
- **Returning `payload`, `sections`, or raw provider/debug blobs in list or detail responses:** the current stored records intentionally keep only `payload_digest` and a trimmed `payload_summary`. [VERIFIED: src/stoa/services/support_destination_service.py]
- **Adding a retry POST that simply calls the Phase 149 delivery endpoint again:** duplicate identical requests already collapse to one `delivery_id`, so a new retry route would be a confusing no-op unless it adds explicit lifecycle-transition semantics. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: tests/test_admin_report_ops.py]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Delivery list pagination tokens | Ad-hoc JSON blobs or unsafe pass-through of DynamoDB keys | Scoped `encode_*_page_token()` / `decode_*_page_token()` helpers that mirror `encode_admin_page_token()` and `decode_admin_page_token()`. [VERIFIED: src/stoa/db/repositories/report_repo.py] | Existing repo tokens already centralize validation and 400 behavior. [VERIFIED: src/stoa/db/repositories/report_repo.py] |
| Delivery audit timeline ordering | In-memory sort of unsorted scan output | Exact-key `query()` on `PK=SUPPORT_HANDOFF_DELIVERY#{delivery_id}` with `SK begins_with("AUDIT#")` and `ScanIndexForward=False`. [VERIFIED: src/stoa/db/repositories/report_repo.py] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html] | DynamoDB already guarantees sort-key order inside a partition. [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html] |
| Privacy filtering | New hand-written denylist separate from the current services | `report_recovery_service.redact_private_artifact_text()` and `release_evidence_service.private_marker_hits()` plus a response allowlist. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: src/stoa/services/release_evidence_service.py] [VERIFIED: src/stoa/services/support_handoff_service.py] | The current delivery/package code already depends on these helpers; splitting the denylist would drift quickly. [VERIFIED: codebase grep] |
| Retry mutation | A broad "re-deliver everything failed" endpoint in Phase 150 | Retry eligibility/status only in Phase 150, then a future bounded mutation phase with conditional updates and worker semantics. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md] | The current `internal_queue` implementation has no lifecycle-update API, no retry worker, and no non-creation audit vocabulary. [VERIFIED: src/stoa/services/support_destination_service.py] |

**Key insight:** The repo already has the right primitives for detail reads and audit timelines; the missing piece is a recent-first list access path plus explicit read-only retry semantics, not a new provider adapter or a broad mutation workflow. [VERIFIED: codebase grep]

## Common Pitfalls

### Pitfall 1: Treating Bounded Scan As "Recent Activity"
**What goes wrong:** The list endpoint appears to work in tests but can return older deliveries ahead of newer ones because bounded scans are not globally time-ordered. [VERIFIED: src/stoa/routers/admin.py] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html]
**Why it happens:** The existing `/admin/reports/ops` fallback uses scan because report ops tolerates pilot-volume triage, but the Phase 150 requirement explicitly asks for recent delivery visibility. [VERIFIED: src/stoa/routers/admin.py] [VERIFIED: .planning/REQUIREMENTS.md]
**How to avoid:** Add a dedicated feed row and query it descending by sort key, or accept scan only as a deliberate temporary fallback documented as approximate. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html]
**Warning signs:** The implementation exposes `access_pattern="bounded_scan"` or sorts only the current page in memory after a scan. [VERIFIED: src/stoa/routers/admin.py]

### Pitfall 2: Reusing Package Validation As Delivery Status
**What goes wrong:** Operators see "generated" or "passed" and cannot tell whether delivery actually queued or was refused. [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]
**Why it happens:** Package generation audit rows and delivery rows are separate concepts, but both currently live near the same support handoff flow. [VERIFIED: src/stoa/services/support_handoff_service.py] [VERIFIED: src/stoa/services/support_destination_service.py]
**How to avoid:** Build list/detail APIs from `SUPPORT_HANDOFF_DELIVERY` rows only, then optionally include the `package_id` as a reference back to package audit. [VERIFIED: src/stoa/db/repositories/report_repo.py]
**Warning signs:** Response models include package `sections`, package `destination.status`, or package audit refs as the primary status field. [VERIFIED: src/stoa/services/support_handoff_service.py]

### Pitfall 3: Shipping A Retry POST Without New State Semantics
**What goes wrong:** A retry endpoint either no-ops by returning the same row via existing idempotency, or it mutates state without an atomic contract and creates confusing audit history. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: tests/test_admin_report_ops.py]
**Why it happens:** Current duplicates are intentionally idempotent and only initial creation writes a delivery audit row. [VERIFIED: src/stoa/services/support_destination_service.py]
**How to avoid:** Keep Phase 150 read-only for retry and return explicit reasons when retry is disabled, especially for privacy-failed and unapproved destinations. [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md] [VERIFIED: .planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md]
**Warning signs:** `retry_count` increments without a new conditional update helper, or the route reuses `POST /admin/reports/support-handoff-delivery` as its only retry implementation. [VERIFIED: codebase grep]

### Pitfall 4: Letting Redacted Reasons Reintroduce Secret Markers
**What goes wrong:** Failure/refusal strings, privacy violations, or provider references leak `weekly-reports/`, `presigned_url`, `authorization`, `cookie`, or free-text secret markers even though raw payloads are omitted. [VERIFIED: src/stoa/services/release_evidence_service.py] [VERIFIED: tests/test_admin_report_ops.py]
**Why it happens:** Metadata-only APIs still move user/operator text, reason strings, and structured violation paths through responses. [VERIFIED: src/stoa/services/support_destination_service.py]
**How to avoid:** Build detail/list responses from a strict allowlist and run the same denylist assertions used in `_assert_no_private_artifact_markers()` against list items, detail payloads, and audit event metadata. [VERIFIED: tests/test_admin_report_ops.py] [VERIFIED: src/stoa/services/release_evidence_service.py]
**Warning signs:** Tests only assert absence of `payload` and `sections`, but do not inspect `refusal_reasons`, `failure_reasons`, `privacy.violations`, `provider_object_url`, and audit `metadata`. [VERIFIED: tests/test_admin_report_ops.py]

## Code Examples

Verified patterns from official sources and the current codebase:

### Existing Admin List Pattern To Mirror
```python
# Source: src/stoa/routers/admin.py
@router.get("/reports/ops", response_model=ReportOperationListResponse)
async def list_report_operations(
    limit: int = Query(default=50, ge=1, le=100),
    next_token: str | None = Query(default=None),
    user: dict = Depends(require_role("admin")),
):
    try:
        last_key = report_repo.decode_admin_page_token(next_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination token") from exc
```

### Existing Descending Audit Query Pattern To Mirror
```python
# Source: src/stoa/db/repositories/report_repo.py
def list_recovery_job_audit_events(job_id: str, *, limit: int = 50, last_key: dict | None = None) -> dict:
    kwargs = {
        "KeyConditionExpression": Key("PK").eq(f"REPORT_RECOVERY_JOB#{job_id}")
        & Key("SK").begins_with("AUDIT#"),
        "Limit": limit,
        "ScanIndexForward": False,
    }
    if last_key:
        kwargs["ExclusiveStartKey"] = last_key
    return get_table().query(**kwargs)
```

### FastAPI Test Override Pattern Already In Use
```python
# Source: tests/test_admin_report_ops.py and FastAPI testing docs
app = FastAPI()
app.include_router(admin.router, prefix="/admin")
app.dependency_overrides[get_current_user] = lambda: {"sub": "admin-sub", "role": "admin"}
app.dependency_overrides[get_settings] = lambda: Settings(support_internal_queue_approved=True)
client = TestClient(app)
```
[VERIFIED: tests/test_admin_report_ops.py] [CITED: https://fastapi.tiangolo.com/advanced/testing-dependencies/]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `preview` / `copy` / `download` package generation only [VERIFIED: src/stoa/services/support_handoff_service.py] | Phase 149 added `internal_queue` delivery summaries and append-only delivery audits. [VERIFIED: src/stoa/services/support_destination_service.py] | 2026-06-12 in Phase 149. [VERIFIED: .planning/phases/149-support-evidence-export-destination-integration/149-01-SUMMARY.md] | Phase 150 should read delivery lifecycle rows, not package audit rows, for operator status visibility. [VERIFIED: .planning/REQUIREMENTS.md] |
| Duplicate requests would normally create duplicate downstream rows [ASSUMED] | Phase 149 collapses identical requests onto one deterministic `delivery_id` and `idempotency_key`. [VERIFIED: src/stoa/services/support_destination_service.py] | 2026-06-12 in Phase 149. [VERIFIED: .planning/phases/149-support-evidence-export-destination-integration/149-01-SUMMARY.md] | Retry mutation now would need explicit new semantics; re-posting identical input is already handled as idempotent reuse. [VERIFIED: tests/test_admin_report_ops.py] |
| Cross-delivery recency is not modeled [VERIFIED: codebase grep] | Phase 150 should introduce a read-optimized delivery feed row or accept an explicitly approximate scan fallback. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html] | Planned for Phase 150. [VERIFIED: .planning/ROADMAP.md] | This is the main storage design decision that controls whether "recent activity" is exact or approximate. [VERIFIED: .planning/REQUIREMENTS.md] |

**Deprecated/outdated:**
- Reading support handoff package audit as the operator queue is outdated for `SUPPORTINT-03`, because the requirement now asks for delivery lifecycle status, retry state, and provider references. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: src/stoa/db/repositories/report_repo.py]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Without a feed row or a new GSI, a bounded scan is only an approximate "recent" list strategy for cross-delivery visibility. [ASSUMED] | `## Summary`, `## Architecture Patterns`, `## Common Pitfalls` | Medium: if table volume is trivial forever, a simpler scan may be acceptable and cheaper to implement. |

## Open Questions

1. **Should Phase 150 backfill any existing Phase 149 delivery rows into the new feed partition if the feed-row strategy is chosen?**
   - What we know: Existing delivery summary rows are keyed only by `delivery_id`, and the current repo has no global recent-delivery query path. [VERIFIED: src/stoa/db/repositories/report_repo.py]
   - What's unclear: Whether any non-test Phase 149 rows already exist and must appear in the first Phase 150 list view. [ASSUMED]
   - Recommendation: If any persisted Phase 149 rows matter operationally, add a small one-time backfill script or lazy repair path; otherwise, document that the recent queue is authoritative from Phase 150 forward. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | backend routes, repo helpers, tests | ✓ [VERIFIED: command run] | `3.14.5` [VERIFIED: local venv import] | — |
| FastAPI in `./.venv` | admin router and `TestClient` tests | ✓ [VERIFIED: command run] | `0.136.3` [VERIFIED: local venv import] | — |
| boto3 in `./.venv` | DynamoDB repository helpers | ✓ [VERIFIED: command run] | `1.43.16` [VERIFIED: local venv import] | — |
| pytest in `./.venv` | verification commands | ✓ [VERIFIED: command run] | `9.0.3` [VERIFIED: local venv import] | — |
| Ruff in `./.venv` | lint verification | ✓ [VERIFIED: command run] | `0.15.14` [VERIFIED: local tool version] | — |
| Node.js | `gsd-tools` plan-structure verification | ✓ [VERIFIED: command run] | `v26.0.0` [VERIFIED: local tool version] | — |
| `ctx7` CLI | preferred docs lookup fallback for libraries | ✗ [VERIFIED: command -v ctx7] | — | Official FastAPI and AWS docs via web were used instead. [CITED: https://fastapi.tiangolo.com/tutorial/query-params-str-validations/] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html] |

**Missing dependencies with no fallback:**
- None. [VERIFIED: command run]

**Missing dependencies with fallback:**
- `ctx7` CLI is missing; official primary-source documentation via web is a viable fallback for this research phase. [VERIFIED: command -v ctx7] [CITED: https://fastapi.tiangolo.com/tutorial/query-params-str-validations/] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` [VERIFIED: local venv import] |
| Config file | `pyproject.toml` via `[tool.pytest.ini_options]` [VERIFIED: pyproject.toml] |
| Quick run command | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` [VERIFIED: command run] |
| Full suite command | `./.venv/bin/pytest -q tests/test_admin_report_ops.py` [VERIFIED: command run] |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SUPPORTINT-03 | Non-admin list and detail requests return `403` without repo reads. [VERIFIED: .planning/REQUIREMENTS.md] | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k "delivery_list_is_admin_only or delivery_detail_is_admin_only"` [ASSUMED] | ❌ Wave 0 |
| SUPPORTINT-03 | List endpoint passes bounded filters (`status`, `destination_mode`, `package_id`, `date_from`, `date_to`, `limit`, `next_token`) into one repo helper and returns metadata-only items plus `next_token`. [VERIFIED: .planning/REQUIREMENTS.md] | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff_delivery_list` [ASSUMED] | ❌ Wave 0 |
| SUPPORTINT-03 | Detail endpoint returns one summary row plus bounded delivery audit events and audit pagination metadata. [VERIFIED: .planning/REQUIREMENTS.md] | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff_delivery_detail` [ASSUMED] | ❌ Wave 0 |
| SUPPORTINT-03 | Retry visibility is explicit and disabled for privacy-failed or unapproved destinations. [VERIFIED: .planning/REQUIREMENTS.md] | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k "retry_visibility and support_handoff"` [ASSUMED] | ❌ Wave 0 |
| SUPPORTINT-03 | Responses and audit metadata do not expose payloads, sections, keys, presigned URLs, auth headers, cookies, or unredacted secret markers. [VERIFIED: .planning/REQUIREMENTS.md] | route/unit | `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k "metadata_only and support_handoff"` [ASSUMED] | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `./.venv/bin/pytest -q tests/test_admin_report_ops.py -k support_handoff` [VERIFIED: command run]
- **Per wave merge:** `./.venv/bin/pytest -q tests/test_admin_report_ops.py` [VERIFIED: command run]
- **Phase gate:** `./.venv/bin/ruff check src/stoa/db/repositories/report_repo.py src/stoa/routers/admin.py src/stoa/services/support_destination_service.py tests/test_admin_report_ops.py` plus the full `tests/test_admin_report_ops.py` run. [VERIFIED: command run]

### Wave 0 Gaps
- [ ] Add list-route coverage in `tests/test_admin_report_ops.py` for admin-only access, filter passthrough, invalid list token, and metadata-only item shaping. [VERIFIED: tests/test_admin_report_ops.py]
- [ ] Add detail-route coverage in `tests/test_admin_report_ops.py` for `404`, invalid audit token, bounded audit paging, and metadata-only audit event shaping. [VERIFIED: tests/test_admin_report_ops.py]
- [ ] Add retry-visibility assertions in list/detail tests instead of a retry POST test, unless the implementation consciously expands scope. [VERIFIED: src/stoa/services/support_destination_service.py] [VERIFIED: .planning/phases/150-operator-queue-and-handoff-status-visibility/150-CONTEXT.md]

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes [VERIFIED: codebase grep] | `Depends(require_role("admin"))` on both list and detail routes. [VERIFIED: src/stoa/routers/admin.py] |
| V3 Session Management | no [VERIFIED: codebase grep] | Session mechanics are outside this phase; the routes consume the existing auth dependency only. [VERIFIED: src/stoa/routers/admin.py] |
| V4 Access Control | yes [VERIFIED: codebase grep] | Keep list/detail/retry visibility admin-only and fail before repo reads in non-admin tests. [VERIFIED: tests/test_admin_report_ops.py] |
| V5 Input Validation | yes [VERIFIED: codebase grep] | Use `Query(..., ge=..., le=...)`, constrained path/query models, and destination/status allowlists. [VERIFIED: src/stoa/routers/admin.py] [CITED: https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/] |
| V6 Cryptography | no [VERIFIED: codebase grep] | The phase only exposes existing SHA-256 digests and must not add custom reversible obfuscation or secret transport. [VERIFIED: src/stoa/services/support_destination_service.py] |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Non-admin operator queue reads | Elevation of Privilege | Route-level `require_role("admin")` plus tests that assert repo functions are not called on `403`. [VERIFIED: src/stoa/routers/admin.py] [VERIFIED: tests/test_admin_report_ops.py] |
| Leakage through metadata fields instead of raw payloads | Information Disclosure | Response allowlist + `private_marker_hits()` + `_assert_no_private_artifact_markers()`-style tests on summary, detail, and audit shapes. [VERIFIED: src/stoa/services/release_evidence_service.py] [VERIFIED: tests/test_admin_report_ops.py] |
| Pagination token tampering | Tampering | Dedicated decode helpers that validate token scope and raise `400` before table access. [VERIFIED: src/stoa/db/repositories/report_repo.py] |
| Retry ambiguity or duplicate queueing | Denial of Service / Repudiation | Keep Phase 150 retry read-only; rely on existing deterministic `delivery_id` reuse until a future mutation phase adds conditional updates. [VERIFIED: src/stoa/services/support_destination_service.py] |
| Misleading "recent" ordering from scan results | Repudiation | Use a feed-query access path for recent-first list semantics or explicitly document scan as approximate pilot behavior. [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html] [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html] |

## Sources

### Primary (HIGH confidence)
- `src/stoa/routers/admin.py` - existing admin list/detail/auth/token patterns and current support handoff delivery route. [VERIFIED: codebase grep]
- `src/stoa/db/repositories/report_repo.py` - current support handoff delivery summary/audit storage and existing pagination helper patterns. [VERIFIED: codebase grep]
- `src/stoa/services/support_destination_service.py` - current lifecycle statuses, idempotency behavior, retry fields, and metadata-only persisted shape. [VERIFIED: codebase grep]
- `tests/test_admin_report_ops.py` - executable baseline for admin-only support handoff package/delivery behavior and privacy assertions. [VERIFIED: codebase grep]
- `.planning/phases/148-support-destination-contract-and-credential-readiness/148-SUPPORT-DESTINATION-CONTRACT.md` - lifecycle vocabulary, refusal rules, and retry contract. [VERIFIED: codebase grep]
- FastAPI Query and validation docs: https://fastapi.tiangolo.com/tutorial/query-params-str-validations/ [CITED: https://fastapi.tiangolo.com/tutorial/query-params-str-validations/]
- FastAPI numeric validation docs: https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/ [CITED: https://fastapi.tiangolo.com/tutorial/path-params-numeric-validations/]
- FastAPI dependency override docs: https://fastapi.tiangolo.com/advanced/testing-dependencies/ [CITED: https://fastapi.tiangolo.com/advanced/testing-dependencies/]
- Boto3 DynamoDB `query()` docs: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html [CITED: https://docs.aws.amazon.com/boto3/latest/reference/services/dynamodb/table/query.html]
- DynamoDB query pagination docs: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html]
- DynamoDB query filter docs: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html]
- DynamoDB scan docs: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html]

### Secondary (MEDIUM confidence)
- `.planning/phases/149-support-evidence-export-destination-integration/149-01-SUMMARY.md` - confirmed Phase 149 outcomes and carried-forward notes. [VERIFIED: codebase grep]
- `.planning/phases/149-support-evidence-export-destination-integration/149-VERIFICATION.md` - confirmed tested behaviors and current route/service boundaries. [VERIFIED: codebase grep]

### Tertiary (LOW confidence)
- None. [VERIFIED: research review]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions were verified locally and the stack already exists in the touched code. [VERIFIED: local venv import] [VERIFIED: codebase grep]
- Architecture: MEDIUM - detail and retry guidance are strongly grounded, but the recommended feed-row list strategy is a design recommendation rather than a currently implemented path. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html]
- Pitfalls: HIGH - each pitfall is directly tied to current code structure or DynamoDB query/scan semantics. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html]

**Research date:** 2026-06-12 [VERIFIED: current_date]  
**Valid until:** 2026-07-12 for codebase-grounded guidance; re-check before planning if Phase 149 storage semantics change. [ASSUMED]
