# Phase 61 Live Verification

**Status:** Partial - read-only production verification passed; safe-fixture mutation blocked.
**Recorded at:** 2026-06-06T17:39:46Z

## Production API Smoke

Script: `/private/tmp/stoa_phase61_api_smoke.mjs`

Safety:

- Used the long-lived secret-backed production admin credential path.
- Did not print password or token.
- Did not call artifact edit, artifact rollback, resend, retry, job create, resume, cancel, or any other report mutation endpoint.

Result:

- API base: `https://api.stoaedu.ch`
- Admin email domain recorded only as `gmail.com`
- `mutationAttempted`: `false`
- `authGatePassed`: `true`
- `healthPassed`: `true`
- `adminListPassed`: `true`
- `privacyPassed`: `true`
- `listCount`: `0`
- `listItemCount`: `0`
- `rollbackActionObserved`: `false` because production list was empty.

Requests:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| POST | `/auth/login` | 200 | `ejBDDg_VZicEJOg=` |
| GET | `/health` | 200 | `ejBDIixc5icEJYQ=` |
| GET | `/admin/reports/ops?limit=1` without token | 401 | `ejBDIjIa5icEJgw=` |
| GET | `/admin/reports/ops?limit=5` | 200 | `ejBDJgjqZicEJ6g=` |
| GET | `/admin/reports/recovery-evidence?limit=1&include_targets=false&include_job_audit=false` | 200 | `ejBDLjQb5icEJnw=` |

Privacy denylist result:

- No `weekly-reports/`
- No `json_s3_key`
- No `html_s3_key`
- No rollback source/target S3 key fields.
- No presigned URL marker.
- No S3 URL.
- No raw report HTML/JSON payload.
- No auth token field in recorded evidence.

## Production Browser Smoke

Script: `/private/tmp/stoa_phase61_browser_smoke.mjs`

Safety:

- Used the long-lived secret-backed production admin credential path.
- Set `localStorage.stoa_access_token` directly to avoid entering secrets into form fields.
- Installed a request guard blocking any non-GET/HEAD/OPTIONS request to `/admin/reports/**`.
- Did not click preview/apply/retry/resend/job/cancel controls.

Result:

- Final URL: `https://app.stoaedu.ch/admin/report-operations`
- Admin role: `admin`
- Route loaded: `true`
- `mutationAttempted`: `false`
- `blockedMutations`: `[]`
- Visible text privacy hits: `[]`
- Screenshot: `/private/tmp/stoa-phase61-production-report-operations.png`

Browser API requests:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| GET | `/admin/reports/ops?status=email_failed&limit=25` | 200 | `ejMukgSA5icEPSw=` |
| GET | `/admin/reports/recovery-jobs` | 200 | `ejMukin5ZicEPHQ=` |

Bundle marker evidence:

- `Artifact rollback`: present.
- `Preview rollback`: present.
- `Apply rollback`: present.
- `artifact-rollback-previews`: present.

Production list was empty during smoke, so the selected-report rollback panel was not visible. Bundle markers prove the deployed frontend contains the v2.2 rollback UI and endpoint path, while browser smoke proved the route/auth/GET/privacy boundary without production mutation.

## Safe-Fixture Mutation Smoke

Default refusal command:

```text
node scripts/report_artifact_safe_fixture_smoke.mjs
```

Result: refused with exit code `2`.

Refusal evidence:

- `mutationAttempted`: `false`
- `refused`: `true`
- `refusalReasons`:
  - `missing --mutate-safe-fixture`
  - `missing fixture name`
  - `missing fixture parent/student/week identifiers`
- `requests`: `[]`

Named safe-fixture mutation smoke was not run because no fixture identity was provided in this session and the production report operations list returned zero rows. This is the correct safety behavior, but it leaves VERIFY-05 incomplete until an explicit non-customer fixture is provided.
