# Phase 47 Context

**Phase:** 47 - Failed/Skipped Subset Resume Backend
**Milestone:** v1.9 Recovery Resume And Support Evidence Packages
**Created:** 2026-06-05

## Context

Phase 46 defined resume jobs as normal recovery jobs that inherit the source job's `job_type` and copy stable source target snapshots into a new pending target set.

Phase 47 implements the backend API surface:

- resume preview
- resume create
- support package export

No new worker event type is needed because resumed jobs reuse existing `resend_email` and `retry_generation` worker routing.

