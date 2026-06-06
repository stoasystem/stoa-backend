# Phase 54: Artifact Editing Contract And CDK Readiness - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Phase 54 produces the implementation contract for backend-mediated, versioned report artifact editing before any mutation code is added. It must define editable artifact fields, storage/versioning, rollback metadata, audit evidence, privacy boundaries, and whether the current CDK resources are sufficient.

</domain>

<decisions>
## Implementation Decisions

### Artifact Contract
- Editable sections must be explicit and bounded; Phase 55 should start with safe structured fields in the JSON artifact, not arbitrary JSON patch or WYSIWYG HTML editing.
- Preview must bind to source report metadata and source artifact metadata so apply can reject stale reports or stale artifacts.
- Version IDs should be backend-generated, deterministic enough for audit correlation, and independent from S3 object keys exposed to clients.
- HTML should be regenerated or sanitized server-side from the edited JSON model; frontend must not submit or receive raw unreviewed HTML.

### Storage And Rollback
- Reuse the private reports bucket and canonical `weekly-reports/{parent_id}/{student_id}/{week_start}/` prefix.
- Current artifacts remain available; apply writes new versioned JSON/HTML objects and only then updates report summary metadata to point at the new current version.
- Rollback metadata records prior current artifact version/key references server-side, but client responses expose only opaque version identifiers and timestamps.
- No broad S3 listing is allowed; all reads/writes use keys derived from report metadata and stored artifact pointers.

### Privacy And Audit
- API responses may include sanitized diff/preview text, validation status, opaque draft/preview IDs, and audit event IDs.
- API responses must omit private S3 keys, presigned URLs, raw JSON, raw unreviewed HTML, auth tokens, and artifact payloads.
- Audit must use the existing report audit timeline and remain append-only, metadata-only, and redacted.
- Refused apply attempts should write audit evidence when a draft becomes stale or validation fails after preview.

### CDK Readiness
- Existing `stoa-reports-*` bucket is private, retained, SSL-enforced, and already grants `stoa-api` `s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` under `weekly-reports/*`.
- Existing DynamoDB table grants `stoa-api` read/write access and can store summary pointers, draft rows, and audit rows under existing `REPORT#{report_id}` partitions.
- No new AWS service, bucket, table, GSI, Lambda, or queue is required for the first implementation.
- If retention/WORM audit is later required, it belongs to a future milestone because current audit is application-enforced append-only rather than compliance-grade immutable storage.

### the agent's Discretion
- Exact field names, response model names, and helper function boundaries may follow backend conventions discovered during implementation.
- The preview diff shape can be text-oriented or structured by field, as long as tests prove the privacy denylist and apply contract.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/report_artifact_service.py` validates canonical artifact keys, reads JSON/HTML from the private reports bucket, and writes JSON/HTML artifacts with content types.
- `src/stoa/services/report_edit_service.py` already provides metadata-only draft/apply validation, stale-draft rejection, private marker detection, and append-only report audit events.
- `src/stoa/db/repositories/report_repo.py` stores report summaries, edit drafts, and audit rows in the existing report partition.
- `src/stoa/routers/admin.py` owns admin-only report operation endpoints and redacts audit metadata before returning it to clients.

### Established Patterns
- Admin mutation endpoints require `Depends(require_role("admin"))`.
- Report mutations use conditional DynamoDB writes against `updated_at` or status fields to reject stale operations.
- Privacy checks redact or reject `weekly-reports/`, `json_s3_key`, `html_s3_key`, `s3_key`, presigned URL markers, and raw HTML markers.
- Phase artifacts should record CDK readiness before implementation because infra is in `/Users/zhdeng/stoa-infra`.

### Integration Points
- Backend implementation should extend report artifact helpers, report repository helpers, report edit service or a sibling artifact edit service, admin router request/response models, and focused pytest coverage.
- CDK readiness depends on `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`, `/Users/zhdeng/stoa-infra/stacks/api_stack.py`, and `/Users/zhdeng/stoa-infra/stacks/database_stack.py`.

</code_context>

<specifics>
## Specific Ideas

- Treat Phase 54 as a non-mutating contract/readiness phase.
- Keep Phase 55 backend-mediated and metadata-safe even though it will read/write private artifacts internally.
- Prefer versioned keys under the existing weekly report prefix rather than a new bucket or public access pattern.

</specifics>

<deferred>
## Deferred Ideas

- Freeform WYSIWYG report editing.
- Raw JSON patch input from frontend.
- Compliance-grade WORM audit storage.
- PDF/multilingual artifact editing.
- New orchestration resources unless Phase 55 discovers a concrete missing access pattern.

</deferred>
