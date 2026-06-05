# Phase 48 Context

**Phase:** 48 - Support Evidence Package UI
**Milestone:** v1.9 Recovery Resume And Support Evidence Packages
**Created:** 2026-06-05

## Context

Phase 47 added backend resume and support package APIs. Phase 48 exposes those capabilities in the existing `/admin/report-operations` recovery jobs panel.

The UI remains metadata-only and keeps mutation controls explicit:

- `Preview resume`
- `Start resume`
- `Support package`

## Constraints

- Preserve existing resend/generation retry UI.
- Keep support package export read-only.
- Enable resume only for selected jobs with resumable target results.
- Keep private artifact markers out of visible UI and Playwright response assertions.

