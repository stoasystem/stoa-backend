# Phase 44 Summary

**Phase:** 44 - Admin Generation Retry Job UI
**Status:** Complete
**Completed:** 2026-06-05

## Completed

- Added frontend API and hook bindings for generation retry recovery job preview/create.
- Converted the async recovery job control panel into a two-mode resend/generation retry UI.
- Added status-specific preview scope and job reason defaults.
- Updated recovery job list rendering for multiple job types.
- Extended Playwright coverage to verify generation retry preview/create and metadata-only rendering.

## Decision

The admin UI can now operate both async resend jobs and async generation retry jobs through the shared recovery job interface. Production smoke in Phase 45 must verify UI availability without starting a production job.

