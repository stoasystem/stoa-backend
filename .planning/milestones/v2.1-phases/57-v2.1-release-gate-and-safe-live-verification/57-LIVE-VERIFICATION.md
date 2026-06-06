# Phase 57 Live Verification

**Status:** Passed
**Recorded at:** 2026-06-06T12:05:00+02:00

## Production API Smoke

Script: `/private/tmp/stoa_phase57_api_smoke.mjs`

Safety:

- Used secret-backed real production admin path.
- Redacted token/password from output.
- No production artifact edit preview, artifact edit apply, report edit draft, recovery retry, resend, job create, resume, or cancel mutation was attempted.

Result:

- API base: `https://api.stoaedu.ch`
- Admin email domain recorded only as `gmail.com`
- `mutationAttempted`: `false`
- `privacyPassed`: `true`
- `authGatePassed`: `true`
- `adminListPassed`: `true`
- `editDraftReadOnlyPassed`: `true`
- `artifactEditPreviewReadOnlyPassed`: `true`

Requests:

| Method | Path | Status | Request ID |
|--------|------|--------|------------|
| POST | `/auth/login` | 200 | `eiKMPh6FZicEJ4Q=` |
| GET | `/health` | 200 | `eiKMxi4j5icEKhw=` |
| GET | `/admin/reports/ops?limit=1` without token | 401 | `eiKMyiXCZicEJgw=` |
| GET | `/admin/reports/ops?limit=5` | 200 | `eiKMyj5qZicEJbA=` |
| GET | `/admin/reports/recovery-evidence?limit=1&include_targets=false&include_job_audit=false` | 200 | `eiKM2gh45icEJuQ=` |

Notes:

- Production report operations list returned `count=0` during smoke.
- Because no report row existed, selected-report read-only checks for nonexistent edit draft and artifact edit preview IDs were skipped rather than creating data.

Privacy denylist result:

- No `weekly-reports/`
- No `json_s3_key`
- No `html_s3_key`
- No `s3_key`
- No presigned URL marker
- No S3 URL
- No raw report HTML/JSON payload
- No auth token field in recorded evidence

## Production Browser Smoke

Script: `/private/tmp/stoa_phase57_browser_smoke.mjs`

Safety:

- Used real admin auth token from secret-backed login.
- Set browser `localStorage.stoa_access_token` directly to avoid entering secrets into form fields.
- Installed request guard blocking any non-GET/HEAD/OPTIONS request to `/admin/reports/**`.
- Did not click create/apply/retry/resend/job/cancel controls.

Result:

- Final URL: `https://app.stoaedu.ch/admin/report-operations`
- Admin role: `admin`
- Route loaded: `true`
- `mutationAttempted`: `false`
- `blockedMutations`: `[]`
- Visible text privacy hits: `[]`
- Screenshot: `/private/tmp/stoa-phase57-production-report-operations.png`

Browser API requests:

| Method | Path | Status | Request ID | Private Hits |
|--------|------|--------|------------|--------------|
| GET | `/admin/reports/recovery-jobs` | 200 | `eiKOxj4LZicEJ6g=` | `[]` |
| GET | `/admin/reports/ops` | 200 | `eiKOxgbb5icEJLg=` | `[]` |

Bundle marker evidence:

- `Create draft`: present
- `Apply draft`: present
- `edit-drafts`: present
- `Artifact edit preview`: present
- `artifact-edit-previews`: present
- `Apply artifact edit`: present

Production list was empty during smoke, so the selected-report artifact edit panel was not visible. Bundle markers prove the deployed frontend includes the v2.1 artifact edit preview/apply UI and API path, while browser smoke proved the route/auth/GET/privacy boundary without production mutation.

## Safe-Fixture Mutation Smoke

No production mutation smoke was performed.

Reason:

- No named non-customer artifact edit safe fixture was selected for v2.1.
- Production report operations list returned zero rows during read-only smoke.
- Local backend tests and frontend Playwright mocks cover preview/apply mutation behavior; production verification intentionally stayed read-only.
