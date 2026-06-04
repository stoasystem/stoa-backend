---
phase: 18-evidence-ledger-milestone-closure
status: passed
score: 0.97
verified: 2026-06-04
requirements: [EVIDENCE-01, EVIDENCE-02, EVIDENCE-03, EVIDENCE-04, EVIDENCE-05]
---

# Phase 18 Verification

## Verdict

`passed`

## Must-Haves

| Requirement | Result | Evidence |
|-------------|--------|----------|
| EVIDENCE-01 | passed | `18-EVIDENCE-LEDGER.md` records backend test commands/results across Phases 14-18, including final `uv run pytest` with 111 passed. |
| EVIDENCE-02 | passed | Ledger records CDK synth evidence for `StoaReportsBucket`, Lambda `S3_REPORTS_BUCKET` env imports, reports bucket IAM grants, retain policies, and clean infra source status. |
| EVIDENCE-03 | passed | Ledger records 2026-06-04 live AWS verification for Lambda env/status, reports bucket privacy/encryption, and deployed Lambda role S3 permissions. |
| EVIDENCE-04 | passed | Ledger records the private-object smoke event invocation, `StatusCode=200`, `status=passed`, `readback_ok=true`, object metadata, private ACL, and `cleanup: not_performed`. |
| EVIDENCE-05 | passed | Ledger records follow-ups for `enforce_ssl=True`, prefix-scoped IAM, lifecycle/smoke cleanup, and broader operational tooling. |

## Automated Checks Run

- `uv run pytest`
  - Result: 111 passed.
- `git diff --check`
  - Result: passed.

## Human Verification

Live AWS verification was completed on 2026-06-04 with AWS SSO profile `stoa`.

- `cdk diff StoaStorageStack StoaApiStack --profile stoa` completed. Storage and dependency stacks had no differences; `StoaApiStack` showed only Lambda `Code.S3Key` asset hash changes from the backend direct-deploy workflow.
- `aws lambda get-function-configuration` confirmed both `stoa-api` and `stoa-weekly-report` are `Active` with `LastUpdateStatus=Successful` and `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- `aws lambda invoke` confirmed deployed private-object smoke passed and read back the S3 artifact.

## Residual Risks

- v1.2 did not add CDK `enforce_ssl`, prefix-scoped IAM, or lifecycle cleanup.
- `cdk diff` shows Lambda code asset hash drift in `StoaApiStack` because backend code is deployed by the backend workflow outside CDK stack deployment. This is expected operationally but should remain visible in future infra reviews.
