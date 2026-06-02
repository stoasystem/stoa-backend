---
phase: 06-cdk-report-automation-foundation
plan: 01
subsystem: infrastructure
tags: [cdk, lambda, eventbridge-scheduler, s3, ses, bedrock, monitoring]
requires:
  - milestone: v1.0
    provides: Parent report lookup and report automation scope
provides:
  - Separate weekly report Lambda infrastructure
  - CDK-defined EventBridge Scheduler target
  - Reports bucket environment and permissions
  - Weekly report failure visibility
  - Importable backend scheduled handler stub
affects: [infrastructure, backend-jobs, reports, monitoring]
tech-stack:
  added: []
  patterns:
    - Scheduled Lambda uses normal handler instead of Mangum/API Gateway
    - CDK grants resources directly where possible
key-files:
  created:
    - src/stoa/jobs/__init__.py
    - src/stoa/jobs/weekly_reports.py
  modified:
    - /Users/zhdeng/stoa-infra/app.py
    - /Users/zhdeng/stoa-infra/stacks/api_stack.py
    - /Users/zhdeng/stoa-infra/stacks/notification_stack.py
    - /Users/zhdeng/stoa-infra/stacks/monitoring_stack.py
key-decisions:
  - "Use a separate stoa-weekly-report Lambda with handler stoa.jobs.weekly_reports.handler."
  - "Place the EventBridge Scheduler target and weekly report DLQ in ApiStack to avoid a NotificationStack <-> ApiStack dependency cycle."
  - "Keep NotificationStack responsible for the schedule group, SES identity, and teacher escalation queue."
  - "Add a safe no-op backend handler stub so the scheduled Lambda is importable before Phase 10 implements orchestration."
patterns-established:
  - "Infrastructure changes that depend on existing stack resources must avoid reverse cross-stack references."
requirements-completed: [CDK-01, CDK-02, CDK-03, CDK-04, CDK-05, CDK-06]
duration: 45min
completed: 2026-06-02
---

# Phase 6 Plan 01 Summary

**CDK weekly report automation foundation with separate scheduled Lambda, scheduler target, retry/failure handling, and monitoring**

## Accomplishments

- Added an importable backend scheduled Lambda entrypoint at `stoa.jobs.weekly_reports.handler`.
- Updated CDK `ApiStack` to accept the existing reports bucket, inject `S3_REPORTS_BUCKET`, and grant report bucket access.
- Added a separate `stoa-weekly-report` Lambda using the existing backend deployment artifact and the normal scheduled handler.
- Granted the report Lambda DynamoDB read/write, reports bucket read/write, Bedrock invoke, and SES send permissions.
- Added an EventBridge Scheduler target, retry policy, and DLQ for weekly report invocation.
- Added CloudWatch alarm and dashboard widgets for weekly report Lambda errors, invocations, and duration.
- Resolved a synth-discovered cross-stack dependency cycle by keeping the scheduler target in `ApiStack` while `NotificationStack` retains the schedule group.

## Task Commits

1. **Backend handler stub** - `3caa608` in `/Users/zhdeng/stoa-backend` (`feat(06): add weekly report job stub`)
2. **CDK infrastructure** - `94e489c` in `/Users/zhdeng/stoa-infra` (`feat(06): add weekly report automation infrastructure`)

## Verification

- `python3 -m py_compile src/stoa/jobs/__init__.py src/stoa/jobs/weekly_reports.py` - passed
- `uv run python -m py_compile app.py stacks/api_stack.py stacks/notification_stack.py stacks/monitoring_stack.py` in `/Users/zhdeng/stoa-infra` - passed
- `npx aws-cdk synth` in `/Users/zhdeng/stoa-infra` - passed after creating the existing required backend `dist/` asset directory

## Issues Encountered

- `uv run cdk synth` failed because no `cdk` executable was installed in the uv environment. Verification used `npx aws-cdk synth`.
- First synth attempt failed because the existing backend `dist/` asset directory was absent. A minimal ignored `dist/` directory was created for synth validation.
- First CDK wiring attempt created an `ApiStack` and `NotificationStack` dependency cycle. The schedule target and DLQ were moved to `ApiStack` while `NotificationStack` kept the schedule group.

## Next Phase Readiness

Phase 7 can build weekly learning aggregation against the existing backend repositories. The infrastructure now exposes the scheduled Lambda entrypoint and report storage permissions that later phases depend on.
