# Next Three Milestones

**Created:** 2026-06-05
**Mode:** autonomous

## v1.8 Incident Generation Retry Jobs

Goal: admins can run bounded async `generation_failed` recovery jobs using the existing recovery job/audit platform and weekly report Lambda, without adding AWS infrastructure by default.

Phases:

- Phase 42: Recovery Job Type Contract And CDK Readiness.
- Phase 43: Async Generation Retry Backend.
- Phase 44: Admin Generation Retry Job UI.
- Phase 45: v1.8 Release Gate And Read-only Production Verification.

Scope:

- Add `retry_generation` async job preview/create/execute/cancel/result/audit support.
- Reuse existing DynamoDB job/target/audit shapes.
- Reuse existing `stoa-weekly-report` worker Lambda invocation model.
- Keep production browser smoke read-only; do not create production generation retry jobs without a named safe fixture.

## v1.9 Recovery Resume And Support Evidence Packages

Goal: admins can resume failed/refused/skipped recovery subsets from a prior job and generate support-safe incident evidence packages.

Planned phases:

- Phase 46: Resume Contract And Evidence Package Design.
- Phase 47: Failed/Skipped Subset Resume Backend.
- Phase 48: Support Evidence Package UI.
- Phase 49: v1.9 Release Gate And Live Verification.

Scope:

- Create a new audit-linked recovery job from a previous job's failed/refused/not_found/skipped targets.
- Support both resend and generation retry resume paths where the original job type permits it.
- Add support-safe package output that bundles job summary, target results, audit timeline, request IDs, and redacted operator notes.
- Do not integrate an external ticketing system unless an approved connector/credential path exists.

## v2.0 Controlled Report Editing MVP

Goal: admins can safely propose and apply bounded report content edits with append-only audit evidence and no direct S3 exposure.

Planned phases:

- Phase 50: Report Editing Contract And Safety Model.
- Phase 51: Backend Report Edit Draft And Apply APIs.
- Phase 52: Admin Report Editing UI.
- Phase 53: v2.0 Release Gate And Final Verification.

Scope:

- Add backend-mediated report edit drafts and apply flow for existing HTML/JSON artifacts.
- Preserve ownership/admin authorization and no public/presigned S3 URLs.
- Record before/after metadata, editor, reason, validation result, and artifact version references in audit evidence.
- Keep PDF generation, multilingual delivery, billing, analytics, and WORM storage out of the MVP unless safety evidence requires them.

