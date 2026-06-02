# Phase 16 Privacy and Ordering Audit

**Audited:** 2026-06-03

## Storage Ordering

`src/stoa/services/report_service.py` builds report metadata, renders HTML, builds JSON, then calls `report_artifact_service.write_report_artifacts(...)` before `report_repo.put_report(...)` and before `notify_service.send_weekly_report_email(...)`.

The resulting order is:

1. JSON artifact `put_object`
2. HTML artifact `put_object`
3. DynamoDB report metadata `put_report`
4. SES weekly report email send

`tests/test_report_service.py` asserts the success order is `s3`, `s3`, `put_report`, `ses`.

`tests/test_report_flow.py` asserts a failure on the second S3 write raises before any metadata write, status update, or SES send. The first JSON write may remain as an orphaned deterministic object, but no parent-visible report metadata or email is created.

## Parent Report Privacy Boundary

Parent report routes in `src/stoa/routers/parents.py` remain backend-mediated:

- `GET /parents/me/children/{child_id}/report`
- `GET /parents/me/children/{child_id}/reports/{week}`
- legacy `GET /parents/{parent_id}/reports/{week}`

The `/parents/me/...` report routes call `_require_child_link(...)` before reading report data, so unlinked child IDs are rejected before report repository access. Existing tests cover unlinked report reads and sibling report data being treated as missing.

`_report_detail_from_item(...)` maps DynamoDB report metadata into `ParentChildReportDetail`; that response model does not include S3 keys, public URLs, or presigned URL fields. `tests/test_parent_children.py` now seeds `s3_key`, `html_s3_key`, and `json_s3_key` in source report items and asserts the API response omits those fields.

## Direct S3 Access Check

No report artifact route exposes public S3 access. The only presign route found is `src/stoa/routers/files.py`, which targets `settings.s3_images_bucket` for image upload PUT URLs, not `settings.s3_reports_bucket`.

Report artifact writes in `report_artifact_service.write_report_artifacts(...)` do not pass ACL parameters and rely on the private bucket plus Lambda IAM verified in Phase 14 and helper tests from Phase 15.

## Residual Risks

- Phase 17 still needs deployed Lambda private-object smoke proof.
- A failed second artifact write can leave an orphaned JSON object. The deterministic key lets retries overwrite it, and future lifecycle cleanup remains tracked for milestone closure.
