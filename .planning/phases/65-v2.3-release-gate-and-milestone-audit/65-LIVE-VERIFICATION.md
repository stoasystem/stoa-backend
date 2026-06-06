# Phase 65 Live Verification

**Status:** Planned
**Recorded at:** TBD

## Production API Smoke

Safety:

- Use the long-lived secret-backed production admin credential path.
- Do not print password, access token, refresh token, cookies, or AWS credentials.
- Do not call artifact edit, artifact rollback, resend, retry, job create, resume, cancel, or any other report mutation endpoint.
- Validate release evidence with a redacted bundle only.

Planned checks:

| Method | Path | Expected | Request ID |
|--------|------|----------|------------|
| POST | `/auth/login` | 200 | TBD |
| GET | `/health` | 200 | TBD |
| POST | `/admin/reports/release-evidence/validate` without token | 401 or 403 | TBD |
| GET | `/admin/reports/release-evidence/fixture-status` without token | 401 or 403 | TBD |
| POST | `/admin/reports/release-evidence/validate` | 200 | TBD |
| GET | `/admin/reports/release-evidence/fixture-status` | 200 | TBD |

Expected result:

- `mutationAttempted`: `false`
- `authGatePassed`: TBD
- `healthPassed`: TBD
- `evidenceValidationPassed`: TBD
- `fixtureStatusPassed`: TBD
- `privacyPassed`: TBD

Privacy denylist:

- No `weekly-reports/`
- No `json_s3_key`
- No `html_s3_key`
- No presigned URL marker.
- No raw report HTML/JSON payload.
- No auth token field in recorded evidence.
- No AWS access key or secret key marker.

## Production Browser Smoke

Safety:

- Use the long-lived secret-backed production admin credential path.
- Set session state without typing secrets into visible form fields.
- Install a request guard blocking any non-GET/HEAD/OPTIONS request to `/admin/reports/**`, except the redacted release evidence validation endpoint if the UI requires POST validation.
- Do not click preview/apply/retry/resend/job/cancel controls.

Planned result fields:

- Final URL: `https://app.stoaedu.ch/admin/report-operations`
- Admin role: `admin`
- Route loaded: TBD
- Release evidence UI marker observed: TBD
- Fixture status UI marker observed: TBD
- `mutationAttempted`: `false`
- `blockedMutations`: TBD
- Visible text privacy hits: TBD
- Screenshot: TBD

Browser API requests:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| TBD | TBD | TBD | TBD |

## Safe-Fixture Mutation Refusal

Default refusal command:

```text
.venv/bin/python scripts/release_evidence.py check-mutation --input <redacted-missing-approval.json>
```

Expected result:

- `mutationAttempted`: `false`
- `refused`: `true`
- Refusal reasons include missing approved fixture name or mutation mode.

## Optional Safe-Fixture Mutation Smoke

Status: Not planned by default.

This section must remain skipped unless explicitly approved for the named non-customer fixture.

If approved, required evidence:

- Fixture name.
- Synthetic parent/student/week identifiers.
- Request IDs.
- Artifact version metadata.
- Cleanup/restore result.
- Privacy denylist result.
- Confirmation that no customer report artifact was mutated.
