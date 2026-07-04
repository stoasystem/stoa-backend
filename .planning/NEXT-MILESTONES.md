# Next Product Milestones

**Updated:** 2026-07-05 after reconciling v5.11 completion and selecting v5.12
**Mode:** internal development, product functionality first

## Current Reality

Completed local milestones:

- v5.10 made email verification, parent account operations, and admin account operations usable in the web frontend.
- v5.11 extended usage ledger coverage beyond question submissions with governed, privacy-safe multi-action events and summaries.

The remaining queue in older `stoa_docs` planning was stale: v5.10 and additional usage ledger coverage are no longer future work.

## Active: v5.12 Curriculum Editor And Content Migration Buildout

**Status:** Active planning
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.12-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.12-REQUIREMENTS.md`

Purpose:

- Implement the rich curriculum editor tooling that v5.1 left as readiness/deferred scope.
- Ensure editing/review/publish/migration actions require backend-granted curriculum capabilities; ordinary teachers/tutors do not receive edit permission by default.
- Add backend draft patch/update, structured validation preview, diff, audit-read, and frontend editor workflows.
- Add production content migration manifest parsing, dry-run/apply APIs, evidence, rollback metadata, and operator UI.
- Preserve published student/parent curriculum reads, adaptive assignment behavior, and usage ledger compatibility.

Detailed build scope:

- Phase 232: Curriculum Buildout Reality Refresh And Contract.
- Phase 233: Backend Special Authorization, Editor Patch, Validation, Diff, And Audit APIs.
- Phase 234: Backend Content Migration Service And APIs.
- Phase 235: Frontend Curriculum Editor And Migration Console.
- Phase 236: v5.12 Curriculum Buildout Release Gate.

## Planned After v5.12

Candidate directions:

- Frontend visual polish for expanded multi-action usage summaries and curriculum content-quality dashboards.
- Live warehouse/BI deployment after migration/content analytics data stabilizes.
- Native/mobile app implementation after web curriculum/account operations are stable.
- Final external payment/support/notification activation when prerequisites unblock.

## Deferred External Activation

- Final live Stripe/TWINT charging still needs approved live credentials, registered production webhook endpoint, TWINT approval, finance acceptance, and explicit rollout enablement.
- Real external support provider and CRM/customer messaging still need approved provider selection, credentials, destination policy, templates, and rollout approval.
- Live notification provider/native push activation remains gated on provider credentials, client implementation, and rollout approval.
- Production warehouse/BI deployment should wait until curriculum migration and content analytics data are stable enough to justify the operational surface.
