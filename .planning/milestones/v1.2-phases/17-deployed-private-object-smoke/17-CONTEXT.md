# Phase 17: Deployed Private-Object Smoke - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning
**Source:** Autonomous smart-discuss path; runtime smoke mechanism phase.

<domain>
## Phase Boundary

This phase adds a narrow weekly report Lambda event path that can prove private S3 read/write access without introducing a public API route or frontend behavior.

In scope:
- Add a `job=report_artifact_s3_smoke` Lambda event path.
- Write one deterministic private JSON object under the canonical `weekly-reports/` prefix.
- Immediately read the same object and verify its content.
- Return bucket, key, content type, readback status, and cleanup decision without returning report content.
- Add local fake-client tests for the smoke path.

Out of scope:
- Public S3 URLs, presigned URLs, frontend S3 access, bucket listing, and access-log verification.
- Automatic smoke object cleanup or lifecycle policy changes.
- Running AWS CLI live smoke from this machine if tooling/credentials are unavailable.
</domain>

<decisions>
## Locked Decisions

- Smoke parent/student identifiers are deterministic backend-safe IDs: `smoke-parent` and `smoke-student`.
- Smoke key defaults to `weekly-reports/smoke-parent/smoke-student/{week_start}/report.json`.
- The smoke path writes JSON only; HTML artifacts remain covered by normal report storage tests.
- Smoke output must not include the JSON artifact content.
- The smoke path is Lambda-event only, not an HTTP route.
</decisions>

<references>
## Canonical References

- `.planning/REQUIREMENTS.md` - SMOKE-01 through SMOKE-05.
- `.planning/phases/15-artifact-key-contract-helper-hardening/15-VERIFICATION.md` - artifact helper key/read/write behavior.
- `.planning/phases/16-storage-failure-ordering-privacy-boundary/16-VERIFICATION.md` - no public/direct S3 parent access.
- `src/stoa/jobs/weekly_reports.py` - scheduled Lambda handler entrypoint.
- `src/stoa/services/report_artifact_service.py` - artifact key and read helper.
- `tests/test_weekly_reports_job.py` - weekly Lambda job tests.
</references>

<risks>
## Risks and Constraints

- This local phase can prove the event path and fake-client read/write behavior; actual deployed Lambda IAM proof still requires invoking the deployed Lambda after packaging/deploy.
- Because automatic cleanup is out of scope, the smoke result should record `cleanup: not_performed`.
