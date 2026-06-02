# Milestone Slice: S3 Report Artifact Infrastructure

**Created:** 2026-06-02
**Status:** Planned
**Parent milestone:** Weekly Report Automation
**Primary repos:**

- Backend: `/Users/zhdeng/stoa-backend`
- Infrastructure/CDK: `/Users/zhdeng/stoa-infra`
- Frontend context: `/Users/zhdeng/stoa-frontend`

## Objective

Make the report artifact storage path deployable and verifiable before implementing full weekly report generation.

The weekly report automation milestone needs to write full report artifacts to S3. This slice focuses only on the infrastructure and backend configuration needed for that:

- Inject `S3_REPORTS_BUCKET` into backend/report Lambdas.
- Grant report bucket read/write permissions.
- Define a stable S3 key contract for report artifacts.
- Verify CDK wiring and deployment readiness.

This slice does not implement report generation, Bedrock report content, SES delivery, or frontend rendering.

## Current Finding

Phase 1 originally identified missing infrastructure:

- `S3_REPORTS_BUCKET` was not injected into backend Lambda.
- Report bucket read/write permissions were missing.

Current CDK inspection shows these items are now present in `/Users/zhdeng/stoa-infra/stacks/api_stack.py`:

- `reports_bucket: s3.Bucket` is accepted by `ApiStack`.
- `S3_REPORTS_BUCKET` is injected into the API Lambda environment.
- `reports_bucket.grant_read_write(self.api_function)` exists.
- A `StoaWeeklyReportFunction` exists with `S3_REPORTS_BUCKET` injected.
- `reports_bucket.grant_read_write(self.weekly_report_function)` exists.
- `app.py` passes `storage.reports_bucket` into `ApiStack`.

Therefore this document treats the work as a verification and hardening slice, not a greenfield design.

## In Scope

- Confirm CDK app synthesizes with reports bucket wiring.
- Confirm API Lambda has `S3_REPORTS_BUCKET`.
- Confirm weekly report Lambda has `S3_REPORTS_BUCKET`.
- Confirm both Lambdas have read/write permissions to the reports bucket.
- Confirm backend settings already expose `settings.s3_reports_bucket`.
- Define report artifact key format.
- Add or plan a minimal backend helper for report artifact writes.
- Add tests or smoke checks for report artifact storage behavior.

## Out of Scope

- EventBridge report schedule logic.
- Bedrock report content generation.
- DynamoDB report metadata model changes.
- SES weekly email delivery.
- Parent frontend report UI.
- PDF generation.
- Report regeneration/admin tooling.

## Required CDK State

### StorageStack

`/Users/zhdeng/stoa-infra/stacks/storage_stack.py` must define:

- Private reports bucket.
- Public access blocked.
- Server access logs enabled.
- Retain policy for report artifacts.

Expected logical resource:

```text
StoaReportsBucket
```

Expected bucket name pattern:

```text
stoa-reports-{account}
```

### ApiStack

`/Users/zhdeng/stoa-infra/stacks/api_stack.py` must:

- Accept `reports_bucket: s3.Bucket`.
- Inject `S3_REPORTS_BUCKET` into API Lambda environment.
- Grant API Lambda read/write access to reports bucket.
- Inject `S3_REPORTS_BUCKET` into weekly report Lambda environment.
- Grant weekly report Lambda read/write access to reports bucket.

Expected environment variable:

```text
S3_REPORTS_BUCKET=<reports bucket name>
```

Expected grants:

```python
reports_bucket.grant_read_write(self.api_function)
reports_bucket.grant_read_write(self.weekly_report_function)
```

### App Wiring

`/Users/zhdeng/stoa-infra/app.py` must pass:

```python
reports_bucket=storage.reports_bucket
```

to `ApiStack`.

## Backend State

`/Users/zhdeng/stoa-backend/src/stoa/config.py` already defines:

```python
s3_reports_bucket: str = "stoa-reports"
```

The Lambda environment variable must override this default in production.

## Artifact Contract

Report artifacts should be private S3 objects. They should not be publicly readable.

Recommended key structure:

```text
reports/{parent_id}/{student_id}/{week_start}/report.json
reports/{parent_id}/{student_id}/{week_start}/report.html
```

Rules:

- `week_start` uses ISO date, e.g. `2026-06-01`.
- `parent_id` and `student_id` must be canonical backend user identifiers.
- Keys must not include email addresses.
- Backend APIs should read/serve report data; frontend should not fetch private S3 objects directly.

## Minimal Backend Helper

This slice may add a small helper before full report generation:

```text
src/stoa/services/report_artifact_service.py
```

Suggested responsibilities:

- Build canonical report artifact S3 keys.
- Write JSON artifact to `settings.s3_reports_bucket`.
- Write HTML artifact to `settings.s3_reports_bucket`.
- Read JSON artifact for backend report detail responses if needed.

Suggested functions:

```python
def build_report_artifact_key(parent_id: str, student_id: str, week_start: str, ext: str) -> str: ...
def put_report_json(parent_id: str, student_id: str, week_start: str, payload: dict) -> str: ...
def put_report_html(parent_id: str, student_id: str, week_start: str, html: str) -> str: ...
def get_report_json(s3_key: str) -> dict: ...
```

If this helper is deferred, the weekly report milestone must implement equivalent functionality before report generation.

## Verification Plan

### CDK Verification

Run in `/Users/zhdeng/stoa-infra`:

```bash
uv run cdk synth
uv run cdk diff StoaApiStack
```

Verify synthesized/diff output includes:

- API Lambda env var `S3_REPORTS_BUCKET`.
- Weekly report Lambda env var `S3_REPORTS_BUCKET`.
- IAM permissions allowing S3 read/write on reports bucket.
- No replacement of the existing reports bucket.

### Backend Configuration Verification

Run in `/Users/zhdeng/stoa-backend`:

```bash
uv run python -c "from stoa.config import settings; print(settings.s3_reports_bucket)"
```

For local dev this may print the default. For deployed Lambda, verify via AWS Lambda configuration or CDK synth output.

### Runtime Smoke Test

After deployment, run a one-off smoke operation against a test key:

```text
reports/smoke/parent-test/student-test/2026-06-01/report.json
```

Expected:

- Lambda can write object to reports bucket.
- Lambda can read object back.
- Object is private.
- No public URL access is required.

## Acceptance Criteria

This slice is complete when:

- CDK synthesizes successfully.
- `StoaApiStack` has no unresolved reference to `reports_bucket`.
- API Lambda receives `S3_REPORTS_BUCKET`.
- Weekly report Lambda receives `S3_REPORTS_BUCKET`.
- API Lambda has reports bucket read/write permission.
- Weekly report Lambda has reports bucket read/write permission.
- A stable report artifact key convention is documented.
- Backend has either a report artifact helper or the weekly report milestone explicitly owns that implementation.
- A deployed smoke test confirms the Lambda can write/read private report artifacts.

## Risks

### CDK Already Changed but Not Deployed

The code may contain the correct wiring while AWS still runs the older stack.

Mitigation:

- Require `cdk diff` and deploy confirmation before starting report generation.

### Wrong Bucket Name in Runtime

`settings.s3_reports_bucket` has a local default, but production must use the CDK-injected value.

Mitigation:

- Verify Lambda environment after deploy.

### Overbroad IAM

Granting `read_write` is acceptable for this MVP slice, but future hardening may restrict keys to `reports/*`.

Mitigation:

- Record this as a follow-up security hardening item if needed.

### Frontend Direct S3 Assumption

Frontend should not fetch report artifacts directly from S3.

Mitigation:

- Parent report API remains the access layer.

## Follow-Up

After this slice is verified, proceed with:

1. `report_service.py` aggregation and artifact writes.
2. Weekly report job handler.
3. DynamoDB metadata updates with `s3_key`.
4. SES email delivery.
5. Parent frontend generated report rendering.
