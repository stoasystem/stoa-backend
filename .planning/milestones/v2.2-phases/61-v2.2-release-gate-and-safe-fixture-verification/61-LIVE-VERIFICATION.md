# Phase 61 Live Verification

**Status:** Passed
**Recorded at:** 2026-06-06T18:49:03Z

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

## Safe-Fixture Mutation Smoke

Fixture:

- `fixtureName`: `stoa-safe-fixture-v2-2-rollback-2026-06-06`
- `parentId`: `safe-fixture-parent-v2-2`
- `studentId`: `safe-fixture-student-v2-2`
- `weekStart`: `2026-06-01`
- `reportId`: `report-safe-fixture-parent-v2-2-safe-fixture-student-v2-2-2026-06-01`

Script:

- Wrapper: `/private/tmp/stoa_phase61_safe_fixture_wrapper.py`
- Harness output: `/private/tmp/stoa_phase61_safe_fixture_smoke.json`

Safety:

- User explicitly approved creating this synthetic non-customer production fixture.
- Fixture summary creation used a conditional DynamoDB put so it could not overwrite an existing summary row.
- The harness used `--mutate-safe-fixture` and the explicit fixture identifiers.
- No password or token was printed.
- All recorded request bodies were sanitized by the harness.

Initial attempt:

- Fixture was created.
- Artifact edit preview succeeded.
- Artifact edit apply returned 409 with `Report artifact changed after preview creation`.
- Diagnosis found that `GSI-ParentId` included artifact edit draft child entities because those entities carried `parent_id`, `student_id`, and `week_start`; selected-report lookup could return the draft instead of `SK=SUMMARY`.
- Fix deployed in `123faad299d0fc6051b7677c8b75cb96df63c9e3`: report parent lookups now filter and enforce `SK == SUMMARY`.

Successful run:

- `mutationAttempted`: `true`
- `refused`: `false`
- `cleanupPassed`: `true`
- `privacyPassed`: `true`
- `fixtureCreated`: `false` on the successful rerun because the summary row was created by the initial approved attempt.

Requests:

| Method | Path | Status | Request ID | Private Hits |
|--------|------|--------|------------|--------------|
| POST | `/auth/login` | 200 | `ejWx4gc25icEMag=` | `[]` |
| GET | `/admin/reports/safe-fixture-parent-v2-2/safe-fixture-student-v2-2/2026-06-01/ops` | 200 | `ejWyYgmPZicEMTw=` | `[]` |
| POST | `/admin/reports/safe-fixture-parent-v2-2/safe-fixture-student-v2-2/2026-06-01/artifact-edit-previews` | 200 | `ejWyahBKZicENGw=` | `[]` |
| POST | `/admin/reports/safe-fixture-parent-v2-2/safe-fixture-student-v2-2/2026-06-01/artifact-edit-previews/4f21cf6387cc48ee888190870472a3ec/apply` | 200 | `ejWyei7y5icEMpQ=` | `[]` |
| POST | `/admin/reports/safe-fixture-parent-v2-2/safe-fixture-student-v2-2/2026-06-01/artifact-rollback-previews` | 200 | `ejWyihBR5icENGw=` | `[]` |
| POST | `/admin/reports/safe-fixture-parent-v2-2/safe-fixture-student-v2-2/2026-06-01/artifact-rollback-previews/9b42e702be4845709ca0cf0cf970f170/apply` | 200 | `ejWyji8F5icEMog=` | `[]` |

Artifact version evidence:

- Initial: `original`
- Edited: `v20260606T184730Z-cb0b33d1`
- Restored: `original`

Cleanup result: passed. The report artifact metadata pointer returned to the initial `original` target after rollback.
