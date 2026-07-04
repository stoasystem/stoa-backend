# Next Product Milestones

**Updated:** 2026-07-05 after completing v5.12 curriculum editor/content migration buildout
**Mode:** internal development, product functionality first

## Current Reality

Completed local milestones:

- v5.10 made email verification, parent account operations, and admin account operations usable in the web frontend.
- v5.11 extended usage ledger coverage beyond question submissions with governed, privacy-safe multi-action events and summaries.
- v5.12 implemented backend and frontend curriculum editor/content migration tooling for backend-authorized curriculum operators.

The remaining queue in older `stoa_docs` planning was stale: v5.10 and additional usage ledger coverage are no longer future work.

## Latest Completed: v5.12 Curriculum Editor And Content Migration Buildout

**Status:** Completed local release gate 2026-07-05
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.12-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.12-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.12-MILESTONE-AUDIT.md`

Purpose:

- Implement the rich curriculum editor tooling that v5.1 left as readiness/deferred scope.
- Ensure editing/review/publish/migration actions require backend-granted curriculum capabilities; ordinary teachers/tutors do not receive edit permission by default.
- Add backend draft patch/update, structured validation preview, diff, audit-read, and frontend editor workflows.
- Add production content migration manifest parsing, dry-run/apply APIs, evidence, rollback metadata, and operator UI.
- Preserve published student/parent curriculum reads, adaptive assignment behavior, and usage ledger compatibility.

Detailed build scope:

- Phase 232: Curriculum Buildout Reality Refresh And Contract. (complete)
- Phase 233: Backend Special Authorization Editor Patch Validation Diff And Audit APIs. (complete)
- Phase 234: Backend Content Migration Service And APIs. (complete)
- Phase 235: Frontend Curriculum Editor And Migration Console. (complete)
- Phase 236: v5.12 Curriculum Buildout Release Gate. (complete)

## Planned After v5.12

These are new functional, safety, and stability milestones. They should not be implemented by renaming v5.12 phases.

### v5.13 Payment And Entitlement Production Completion

Roadmap: `.planning/milestones/v5.13-ROADMAP.md`
Requirements: `.planning/milestones/v5.13-REQUIREMENTS.md`

Purpose:

- Make paid access work end to end for real users.
- Complete checkout/paywall state, provider event reconciliation, entitlement activation, quota compatibility, refund/cancellation/invoice support state, and admin billing evidence.
- Start with a reality audit so existing readiness docs do not mask broken or stubbed behavior.

### v5.14 Verification And Login Reliability

Roadmap: `.planning/milestones/v5.14-ROADMAP.md`
Requirements: `.planning/milestones/v5.14-REQUIREMENTS.md`

Purpose:

- Make email verification, resend/confirm, login-code/passwordless policy, account activation, and support recovery reliable.
- Ensure frontend and backend agree on blocked, pending, confirmed, expired, wrong-code, and provider-failure states.
- Remove or clearly disable any half-enabled login-code behavior.

### v5.15 Usage, Quota, And Product Stability

Roadmap: `.planning/milestones/v5.15-ROADMAP.md`
Requirements: `.planning/milestones/v5.15-REQUIREMENTS.md`

Purpose:

- Make usage accounting and quota behavior trustworthy across real student flows.
- Reconcile ledger rows, aggregate counters, entitlement limits, and support summaries.
- Add core health/smoke gates for login, entitlement, curriculum read, question submit, teacher help, and admin support surfaces.

## Deferred External Activation

- Final live Stripe/TWINT charging still needs approved live credentials, registered production webhook endpoint, TWINT approval, finance acceptance, and explicit rollout enablement.
- Real external support provider and CRM/customer messaging still need approved provider selection, credentials, destination policy, templates, and rollout approval.
- Live notification provider/native push activation remains gated on provider credentials, client implementation, and rollout approval.
- Production warehouse/BI deployment should wait until curriculum migration and content analytics data are stable enough to justify the operational surface.
