# Phase 43 Context

**Phase:** 43 - Async Generation Retry Backend
**Milestone:** v1.8 Incident Generation Retry Jobs
**Created:** 2026-06-05
**Status:** Complete

## Inputs

- Phase 42 contract and CDK readiness approved reuse of existing resources.
- Existing service supports async `resend_email` jobs.
- Existing single-report generation retry service handles report generation, artifact storage, email delivery, status updates, and report audit.

## Scope

Add backend support for async `retry_generation` jobs:

- Preview endpoint.
- Create endpoint.
- Worker event routing.
- Stable target snapshots.
- Job/target/audit updates.
- Generic cancellation.
- Focused tests.

## Safety

This phase adds production-capable mutation endpoints but does not execute production mutation. Production validation remains read-only until Phase 45.

