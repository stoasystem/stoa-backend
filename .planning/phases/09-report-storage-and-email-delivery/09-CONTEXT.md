# Phase 9: Report Storage and Email Delivery - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase makes generated weekly report content durable before delivery and preserves report availability if email delivery fails. It owns DynamoDB report metadata, private S3 JSON/HTML artifacts, SES parent email composition/sending, and email-failure status updates. It does not implement scheduled pair discovery/idempotency or parent API/frontend rendering changes.

</domain>

<decisions>

## Implementation Decisions

### Storage Contract

- Use existing `report_repo.put_report` and `GSI-ParentId` parent/week lookup patterns.
- Store report metadata with a stable report id derived from `(parent_id, student_id, week_start)`.
- Include legacy fields already consumed by parent routes (`usage_count`, `ai_resolved`, `teacher_resolved`, `weak_knowledge_points`, `recommendations`) while also adding generated-content fields needed by later phases.
- Store artifacts before email is attempted so `email_failed` reports remain available.

### Artifact Contract

- Store JSON and HTML artifacts in the private reports S3 bucket from `settings.s3_reports_bucket`.
- Use deterministic keys under `weekly-reports/{parent_id}/{student_id}/{week_start}/`.
- Keep report HTML simple and parent-facing; no external assets are required.

### Email Contract

- Send only to `payload["parent"]["email"]`.
- Email content includes student name, week range, summary, recommendations, and a parent portal link placeholder/path.
- If SES fails, update the stored report status to `email_failed` with error fields rather than deleting or hiding the generated report.

### Logging/Safety Contract

- Logs may include report id, parent/student/week identifiers, counts, and error class names.
- Logs must not include full student question content or raw activity summaries.

### the agent's Discretion

The agent may choose helper names and exact metadata field names, provided later phases can read generated report detail and email status from the stored item.

</decisions>

<code_context>

## Existing Code Insights

### Reusable Assets

- `src/stoa/services/report_service.py` now provides aggregation, compact Bedrock input, strict generated content parsing, generation, and fallback content.
- `src/stoa/db/repositories/report_repo.py` exposes `put_report`, `get_report_by_week`, and `list_reports_for_parent` over the report single-table item shape.
- `src/stoa/services/notify_service.py` already sends SES email but only accepts a bare HTML body.
- `src/stoa/config.py` exposes `settings.s3_reports_bucket`.
- CDK Phase 6 grants both API and weekly-report Lambdas read/write access to the reports bucket and DynamoDB table.

### Established Patterns

- Backend storage helpers are simple functions and dictionaries.
- Tests use fake clients and monkeypatches instead of real AWS.
- Existing parent routes still expect legacy report fields until Phase 11 expands the response model.

### Integration Points

- Phase 10 will call the storage/email function for eligible parent/student/week pairs and rely on status fields for counts.
- Phase 11 will expose stored generated content and email status through the parent API and frontend.

</code_context>

<specifics>

## Specific Ideas

- Add `store_and_send_weekly_report(payload, generated_content, s3_client=None, ses_client=None, now=None)` to `report_service.py`.
- Add `report_repo.update_report_status(report_id, status, **fields)` for email failure/success updates.
- Add `notify_service.send_weekly_report_email(parent_email, report_html, *, subject=None, ses_client=None)` while preserving backward compatibility with existing call sites.

</specifics>

<deferred>

## Deferred Ideas

- Scheduled idempotent orchestration and pair discovery belong to Phase 10.
- Parent API/frontend response expansion belongs to Phase 11.
- Broader backend integration tests belong to Phase 12.

</deferred>
