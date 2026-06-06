# Phase 65 Live Verification

**Status:** Passed
**Recorded at:** 2026-06-06T22:37:33Z

## Production API Smoke

Safety:

- Used the long-lived secret-backed production admin credential path through AWS Secrets Manager.
- Did not print password, access token, refresh token, cookies, or AWS credentials.
- Did not call artifact edit, artifact rollback, resend, retry, job create, resume, cancel, or any other report mutation endpoint.
- Validated release evidence with a redacted bundle only.

Result:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| POST | `/auth/login` | 200 | `ej4SAip6ZicEPSw=` |
| GET | `/health` | 200 | `ej4SEjj85icEPfQ=` |
| POST | `/admin/reports/release-evidence/validate` without token | 401 | `ej4SFgtz5icEPgA=` |
| GET | `/admin/reports/release-evidence/fixture-status?fixture_name=stoa-safe-fixture-v2-2-rollback-2026-06-06` without token | 401 | `ej4SFh-ZZicEP2w=` |
| POST | `/admin/reports/release-evidence/validate` | 200 | `ej4SFgNv5icEPSA=` |
| GET | `/admin/reports/release-evidence/fixture-status?fixture_name=stoa-safe-fixture-v2-2-rollback-2026-06-06` | 200 | `ej4SGjj_ZicEPfQ=` |

Summary:

- `mutationAttempted`: `false`
- `authGatePassed`: `true`
- `healthPassed`: `true`
- `evidenceValidationPassed`: `true`
- `fixtureStatusPassed`: `true`
- `fixtureStatus`: `ready`
- `privacyPassed`: `true`

Privacy denylist result:

- No `weekly-reports/`
- No `json_s3_key`
- No `html_s3_key`
- No presigned URL marker.
- No raw report HTML/JSON payload.
- No auth token field in recorded evidence.
- No AWS access key or secret key marker.

## Production Browser Smoke

Safety:

- Used the long-lived secret-backed production admin credential path.
- Set session state without typing secrets into visible form fields.
- Installed a request guard blocking non-GET/HEAD/OPTIONS requests to `/admin/reports/**`, except the redacted release evidence validation endpoint if explicitly triggered.
- Did not click preview/apply/retry/resend/job/cancel controls.

Result:

- Final URL: `https://app.stoaedu.ch/admin/report-operations`
- Admin role: `admin`
- Route loaded: `true`
- Release evidence UI marker observed: `true`
- Fixture status UI marker observed: `true`
- `mutationAttempted`: `false`
- `blockedMutations`: `[]`
- Visible text privacy hits: `[]`
- Screenshot: `/private/tmp/stoa-phase65-production-report-operations.png`

Browser API requests:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| GET | `/admin/reports/recovery-jobs` | 200 | `ej4aohJH5icEJgw=` |
| GET | `/admin/reports/ops?status=email_failed&limit=25` | 200 | `ej4aojqoZicEJfA=` |
| GET | `/admin/reports/release-evidence/fixture-status?fixture_name=stoa-safe-fixture-v2-2-rollback-2026-06-06` | 200 | `ej4auicFZicEJQA=` |

## Safe-Fixture Mutation Refusal

Default release-evidence refusal command:

```text
.venv/bin/python scripts/release_evidence.py check-mutation --output /private/tmp/stoa_phase65_mutation_refusal_result.json
```

Result:

- `allowed`: `false`
- Refusal reasons: `missing fixture name`, `missing mutation mode`, `fixture status unknown is not mutation-ready`.

Existing safe-fixture harness default refusal:

```text
node scripts/report_artifact_safe_fixture_smoke.mjs --output /private/tmp/stoa_phase65_safe_fixture_default_refusal.json
```

Result:

- Exit status: `2`
- `mutationAttempted`: `false`
- `refused`: `true`
- Refusal reasons: `missing --mutate-safe-fixture`, `missing fixture name`, `missing fixture parent/student/week identifiers`.
- Requests: `[]`

## Optional Safe-Fixture Mutation Smoke

Status: Skipped.

Reason: Phase 65 had approval to push/deploy and run read-only release verification. It did not have explicit approval to mutate the named fixture again. The release gate therefore records fixture readiness and refusal behavior only.

Required evidence if approved in a future release:

- Fixture name.
- Synthetic parent/student/week identifiers.
- Request IDs.
- Artifact version metadata.
- Cleanup/restore result.
- Privacy denylist result.
- Confirmation that no customer report artifact was mutated.
