# v1.2 S3 Report Artifact Infrastructure Evidence Ledger

**Closed:** 2026-06-03
**Milestone:** v1.2 S3 Report Artifact Infrastructure

## Backend Test Evidence

| Command | Result | Coverage |
|---------|--------|----------|
| `PYTHONPATH=src pytest tests/test_report_service.py tests/test_report_flow.py` | 24 passed, 1 warning | Phase 14 production reports bucket guard and report flow storage behavior. |
| `PYTHONPATH=src pytest tests/test_report_artifact_service.py tests/test_report_service.py tests/test_report_flow.py tests/test_weekly_reports_job.py` | 49 passed, 1 warning | Phase 15 artifact helper/key/read/write contract. |
| `uv run pytest` | 109 passed | Phase 15 full suite after helper hardening. |
| `uv run pytest` | 109 passed | Phase 16 full suite after storage ordering/privacy tests. |
| `uv run pytest` | 111 passed | Phase 17 full suite after smoke event path. |

`PYTHONPATH=src pytest` with system Python failed for the full suite because system Python did not have `python-jose`; `uv run pytest` uses the declared project environment and passed.

## CDK and Runtime Configuration Evidence

Phase 14 ran `uv run python app.py` from `/Users/zhdeng/stoa-infra` and synthesized CDK output successfully. JSII emitted a Node 26 unsupported-version warning, but synth completed.

Synth evidence from `/Users/zhdeng/stoa-infra/cdk.out`:

- `StoaStorageStack.template.json` contains `StoaReportsBucket2B5C0997`.
- Reports bucket has `DeletionPolicy: Retain` and `UpdateReplacePolicy: Retain`.
- Reports bucket name is `stoa-reports-562923011260`.
- Public access block sets all four public access controls to true.
- Bucket encryption uses SSE-S3 `AES256`.
- Access logging targets `StoaLogsBucket` with `LogFilePrefix: reports/`.
- `git -C /Users/zhdeng/stoa-infra status -sb` was clean after synth.

Lambda env/IAM synth evidence from `StoaApiStack.template.json`:

- `stoa-api` receives `S3_REPORTS_BUCKET` from the StorageStack reports bucket import.
- `stoa-weekly-report` receives `S3_REPORTS_BUCKET` from the StorageStack reports bucket import.
- Both Lambda role policies include reports bucket ARN resources and S3 read/write actions.

Not run locally:

- `cdk diff`, because `cdk` CLI is not installed on PATH.
- Live Lambda env/IAM AWS queries, because `aws` CLI is not installed on PATH.

## Backend Artifact Contract Evidence

Phase 15 added `src/stoa/services/report_artifact_service.py`:

- `build_report_artifact_keys(...)` emits only `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- Parent/student IDs must match safe backend identifier characters and reject email/display/slash/blank inputs.
- `week_start` parses through `date.fromisoformat()` and emits normalized `YYYY-MM-DD`.
- `write_report_artifacts(...)` writes JSON then HTML to `settings.report_artifacts_bucket` with content types `application/json` and `text/html; charset=utf-8`.
- Tests assert no `ACL` parameter is sent.
- `get_report_json(...)` reads and decodes canonical JSON artifact keys.

## Storage Ordering and Privacy Evidence

Phase 16 verifies ordering and privacy boundaries:

- Success order remains S3 JSON write, S3 HTML write, DynamoDB metadata write, SES send.
- Failure on the second S3 write records only two S3 attempts and no metadata/status/email side effects.
- Parent report detail responses omit `s3_key`, `html_s3_key`, `json_s3_key`, direct public URL fields, and presigned URL fields even when source report metadata contains S3 keys.
- `/parents/me/...` report routes remain ownership-checked before report reads.
- `/files/presign` remains image upload-only and targets `settings.s3_images_bucket`, not report artifacts.

See `16-PRIVACY-AUDIT.md` for route-level details.

## Private-Object Smoke Evidence

Phase 17 added a weekly Lambda event-only smoke path:

```json
{"job":"report_artifact_s3_smoke","week_start":"2026-06-01"}
```

Local fake-client tests prove the smoke path:

- Routes through `weekly_reports.handler(...)` without running the scheduled weekly report job.
- Writes one deterministic JSON object at `weekly-reports/smoke-parent/smoke-student/2026-06-01/report.json`.
- Reads the same private object back through `get_object`.
- Returns only `status`, `bucket`, `key`, `content_type`, `readback_ok`, and `cleanup`.
- Does not return object content, public URLs, presigned URLs, bucket listings, or access-log evidence.
- Records `cleanup: not_performed`.

Live deployed smoke was not invoked locally because AWS CLI is unavailable.

Deploy-capable follow-up command:

```text
aws lambda invoke \
  --function-name stoa-weekly-report \
  --payload '{"job":"report_artifact_s3_smoke","week_start":"2026-06-01"}' \
  /tmp/stoa-report-artifact-smoke.json
```

Expected result: `status=passed`, `readback_ok=true`, `content_type=application/json`, `key` under `weekly-reports/`, no report content in output.

## Follow-Ups

- Add `enforce_ssl=True` to the reports bucket in CDK.
- Scope reports bucket IAM grants to the canonical `weekly-reports/*` prefix after confirming no non-report objects are needed.
- Add lifecycle cleanup or explicit delete behavior for smoke artifacts and orphaned first JSON writes.
- Add operational tooling for report delivery retry/resend, artifact health, and admin/support visibility.
- Run live AWS Lambda env/IAM verification and deployed smoke in a deploy-capable environment.
