---
phase: 14-cdk-runtime-configuration-verification
status: passed
score: 0.88
verified: 2026-06-03
requirements: [INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05]
---

# Phase 14 Verification

## Verdict

`passed`

Phase 14 passes for source/synth-backed infrastructure verification and production runtime guard behavior. Live deployed AWS state was not queried because `aws` CLI is not installed locally; this is recorded as evidence debt for Phase 18 rather than treated as completed deployed-state proof.

## Must-Haves

| Requirement | Result | Evidence |
|-------------|--------|----------|
| INFRA-01 | passed | `uv run python app.py` synthesized CDK output. `StoaStorageStack.template.json` contains `StoaReportsBucket2B5C0997` with `DeletionPolicy: Retain`, `UpdateReplacePolicy: Retain`, `BucketName: stoa-reports-562923011260`, full public access block, SSE-S3 `AES256`, and access logging to `StoaLogsBucket` with `LogFilePrefix: reports/`. No Phase 14 code changes modified `/Users/zhdeng/stoa-infra/stacks/storage_stack.py`; `git -C /Users/zhdeng/stoa-infra status -sb` was clean. |
| INFRA-02 | passed | `StoaApiStack.template.json` shows `StoaApiFunctionC79E3275` / `FunctionName: stoa-api` with `Environment.Variables.S3_REPORTS_BUCKET` imported from `StoaStorageStack:ExportsOutputRefStoaReportsBucket2B5C099728B70FE0`. |
| INFRA-03 | passed | `StoaApiStack.template.json` shows `StoaWeeklyReportFunctionF0574091` / `FunctionName: stoa-weekly-report` with `Environment.Variables.S3_REPORTS_BUCKET` imported from `StoaStorageStack:ExportsOutputRefStoaReportsBucket2B5C099728B70FE0`. |
| INFRA-04 | passed | `StoaApiFunctionServiceRoleDefaultPolicyA7202E0D` and `StoaWeeklyReportFunctionServiceRoleDefaultPolicyCAB3D477` both include allow statements for reports bucket ARN resources with S3 read/write actions including `s3:GetObject*`, `s3:PutObject`, `s3:List*`, and related object tagging/retention actions. |
| INFRA-05 | passed | `src/stoa/config.py` adds `Settings.report_artifacts_bucket`, which raises `ValueError` in production for blank or `stoa-reports`; `src/stoa/services/report_service.py` uses this accessor before S3 writes. `tests/test_report_service.py` covers development placeholder allowance, production placeholder rejection, blank production rejection, trimmed production CDK bucket acceptance, and report storage fail-closed behavior before S3/DynamoDB/SES. |

## Automated Checks Run

- `pytest tests/test_report_service.py tests/test_report_flow.py`
  - Result: failed during collection because system Python did not have `src` on import path (`ModuleNotFoundError: No module named 'stoa'`).
- `PYTHONPATH=src pytest tests/test_report_service.py tests/test_report_flow.py`
  - Result: 24 passed, 1 warning.
- `uv run python app.py` from `/Users/zhdeng/stoa-infra`
  - Result: success; JSII emitted an untested Node 26 warning.
- `python -c '...'` JSON parser over synthesized `StoaStorageStack.template.json` and `StoaApiStack.template.json`
  - Result: printed reports bucket, Lambda env var, and IAM policy evidence listed above.
- `which aws` and `aws --version`
  - Result: AWS CLI not installed.
- `which cdk`
  - Result: CDK CLI not installed.
- `git -C /Users/zhdeng/stoa-infra status -sb`
  - Result: `## main...origin/main`.

## Human Verification

None required for source/synth verification. Deployed-state verification remains incomplete until a machine with AWS CLI/CDK CLI and credentials checks live Lambda configuration and IAM policies.

## Residual Risks

- `cdk diff` was not run because the CDK CLI is not installed on PATH.
- Live deployed Lambda env vars and IAM policies were not queried because AWS CLI is not installed on PATH.
- JSII warned that Node 26 is not a tested runtime for the current CDK library. Synth still completed, but future infra verification should prefer a supported Node version.
- Later phases still need private-object runtime smoke proof and artifact key/helper hardening.
