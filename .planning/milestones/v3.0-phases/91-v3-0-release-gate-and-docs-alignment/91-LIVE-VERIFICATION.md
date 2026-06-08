# Phase 91 Live Verification: v3.0 Release Gate

**Verified:** 2026-06-08  
**Mode:** Production non-mutating verification

## Local Quality Gates

- Full backend tests: `PYTHONPATH=src .venv/bin/python -m pytest -q`
  - Result: `263 passed in 3.71s`
- Phase 89 focused ruff:
  - Result: `All checks passed`
- Phase 90 focused ruff:
  - Result: `All checks passed`

## Backend Deploy Evidence

Primary v3.0 backend deploy:

- Repository: `stoasystem/stoa-backend`
- Branch: `main`
- Head SHA: `d8acc08831905cdf46d3489a866e4ef5b41579dc`
- Workflow: `Deploy Backend`
- Run ID: `27106207390`
- Result: `completed / success`
- URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27106207390`

API route fix and Lambda restore:

- Infra repository: `stoasystem/stoa-infra`
- Infra commit: `a4d5cfe`
- Change: added public API Gateway routes for `/auth/forgot-password` and `/auth/reset-password`.
- CDK deploy: `cdk deploy StoaApiStack --context env=prod --require-approval never --exclusively`
- API stack result: `UPDATE_COMPLETE`
- Backend redeploy commit: `8dd5109326691d9bd62fbb16fb1b4155cb78fa73`
- Backend redeploy workflow run: `27107587269`
- Result: `completed / success`
- URL: `https://github.com/stoasystem/stoa-backend/actions/runs/27107587269`

Release-gate issue found and fixed:

- Initial smoke after backend deploy returned `401` for forgot/reset because API Gateway public route allowlist did not include the new auth endpoints.
- A first non-exclusive CDK deploy attempt touched dependency stacks and failed on an unrelated `StoaNotificationStack` SES identity update, then rolled back.
- The API route fix was deployed with `--exclusively` to update only `StoaApiStack`.
- CDK route deployment also redeployed Lambda from a local skip-install asset, causing temporary `/health` 500 responses.
- Backend GitHub deploy run `27107587269` restored the valid Lambda package.

## Final Lambda Runtime State

```json
{
  "FunctionName": "stoa-api",
  "Runtime": "python3.12",
  "LastModified": "2026-06-07T23:07:30.000+0000",
  "State": "Active",
  "LastUpdateStatus": "Successful",
  "CodeSha256": "KJ3HVfeJyF4S+2w0CnwfNJNzxS3b+EwtrW6QDozd5y4=",
  "Version": "$LATEST"
}
```

## Final Production Smoke

API base: `https://api.stoaedu.ch`  
Timestamp: `2026-06-08T00:16:18.391Z`  
Mutation attempted: `false`

| Check | Method | Path | Status | Request ID |
|-------|--------|------|--------|------------|
| Health | GET | `/health` | 200 | `enZ4hg2W5icEPfQ=` |
| Forgot unknown account | POST | `/auth/forgot-password` | 200 | `enZ41gbi5icEQ2g=` |
| Reset unknown account | POST | `/auth/reset-password` | 400 | `enZ47gxFZicEPgQ=` |
| Question auth gate | POST | `/questions` | 401 | `enZ47hrV5icEPSA=` |

Privacy denylist:

- `accessToken`: absent
- `refresh_token`: absent
- `id_token`: absent
- report artifact private markers: absent
- `image_s3_key` with value: absent

Result: passed.

## Residual Risk

- The unrelated `StoaNotificationStack` SES identity drift remains a separate infrastructure concern; it was not required for v3.0 API route deployment and was rolled back by CloudFormation.
- Formal legal/compliance approval of retention policy remains outside v3.0 and was not fabricated.

