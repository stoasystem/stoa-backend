# Phase 14: CDK & Runtime Configuration Verification - Context

**Gathered:** 2026-06-03
**Status:** Ready for planning
**Source:** Autonomous smart-discuss path; infrastructure-only phase, no user-facing grey areas.

<domain>
## Phase Boundary

This phase proves the existing CDK/runtime configuration is ready for private weekly report artifact storage. It does not introduce a new bucket, API route, parent frontend behavior, smoke event, or artifact helper extraction.

In scope:
- Verify `StoaReportsBucket` source/synth configuration remains private, retained, encrypted, access-logged, and unreplaced by the planned change.
- Verify CDK injects `S3_REPORTS_BUCKET` into both `stoa-api` and `stoa-weekly-report`.
- Verify CDK grants both Lambdas read/write access to the reports bucket.
- Harden production backend behavior so missing CDK-injected bucket configuration cannot silently use the local `stoa-reports` placeholder.
- Record durable evidence for Phase 18 closure.

Out of scope:
- Changing the canonical artifact key contract.
- Adding S3 read helpers or smoke events.
- Changing parent report APIs or frontend behavior.
- Manually patching deployed AWS resources outside CDK.
</domain>

<decisions>
## Locked Decisions

- Keep the canonical artifact key prefix from v1.2 requirements: `weekly-reports/{parent_id}/{student_id}/{week_start}/report.{json,html}`.
- Keep reports bucket private and backend-mediated; no public S3 URLs, public ACLs, bucket website hosting, or client direct S3 fetch.
- Treat CDK source evidence separately from deployed AWS evidence. Source/synth confidence can pass this phase; deployed-state gaps must be explicitly recorded if AWS CLI/CDK diff cannot be run.
- Preserve local development default `s3_reports_bucket = "stoa-reports"` for non-production environments.
- In `ENVIRONMENT=production`, report artifact storage must reject blank or placeholder `S3_REPORTS_BUCKET` before issuing S3 writes.
</decisions>

<references>
## Canonical References

- `.planning/ROADMAP.md` - Phase 14 scope and success criteria.
- `.planning/REQUIREMENTS.md` - INFRA-01 through INFRA-05.
- `.planning/research/SUMMARY.md` - research conclusion that v1.2 is verification/hardening, not greenfield infrastructure.
- `/Users/zhdeng/stoa-infra/stacks/storage_stack.py` - `StoaReportsBucket` CDK source.
- `/Users/zhdeng/stoa-infra/stacks/api_stack.py` - Lambda env vars and bucket grants.
- `/Users/zhdeng/stoa-infra/app.py` - storage-to-api stack wiring.
- `src/stoa/config.py` - backend runtime settings.
- `src/stoa/services/report_service.py` - current S3 report artifact writes.
</references>

<risks>
## Risks and Constraints

- `stoa-infra` is outside this workspace's writable root; infra verification commands that write `cdk.out` require approval/escalation.
- CDK source can be correct while deployed Lambda configuration is stale. This phase must not overstate deployed confidence if AWS CLI verification is unavailable.
- The Lambda deployment package uses gitignored `stoa-backend/dist`; deployed smoke confidence later depends on a fresh packaged asset.
- The production guard must not break existing local tests that monkeypatch `settings.s3_reports_bucket`.
</risks>
