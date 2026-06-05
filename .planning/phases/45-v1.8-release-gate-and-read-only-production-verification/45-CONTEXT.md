# Phase 45 Context

**Phase:** 45 - v1.8 Release Gate And Read-only Production Verification
**Milestone:** v1.8 Incident Generation Retry Jobs
**Created:** 2026-06-05

## Context

Phases 42-44 delivered bounded async `retry_generation` recovery jobs:

- Phase 42 defined the job contract and confirmed no new AWS resources were required.
- Phase 43 implemented backend preview/create/execute/cancel/result/audit support.
- Phase 44 added frontend job type selection and e2e coverage for resend and generation retry jobs.

Phase 45 closes v1.8 with deploy evidence, Lambda manifest/runtime evidence, CDK diff classification, production read-only API checks, production browser smoke, and final milestone audit.

## Release Safety

- Production verification must not start a recovery job.
- Browser routing must block non-GET `/admin/reports/**` requests.
- Live checks may authenticate with the long-lived secret-backed production admin path.
- Live checks may call read-only admin GET APIs.
- Secrets must not be printed or committed.

