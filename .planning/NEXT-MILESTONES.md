# Next Three Milestones

**Updated:** 2026-06-15 after selecting v5.4
**Mode:** product functionality first

## Latest Completed: v5.3 Controlled Assignment Automation

**Status:** Completed local release gate 2026-06-15
**Roadmap archive:** `.planning/milestones/v5.3-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v5.3-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.3-MILESTONE-AUDIT.md`

Goal: convert v5.2 recommendations into controlled assignment automation from reviewed sources.

Closed scope:

- Added policy-bounded preview, approved-batch execution, deterministic source idempotency, per-item result evidence, and role-safe automation metadata.
- Closed as `automation-ready`; frontend implementation, live notification delivery, native apps, live warehouse/BI, fully unreviewed autonomous tutoring, and external provider activation remain future scope.

## Active v5.4 Frontend Learning Operations And Automation Dashboards

**Status:** Active planning 2026-06-15
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`

Function purpose:

- Make v5.2/v5.3 backend learning operations usable in frontend tutor/admin/student/parent workflows.
- Let operators preview and execute automated assignment batches, inspect analytics, and review intervention opportunities.
- Let students/parents understand automated assignments without exposing answer keys or ranking internals.
- This is not automatic teacher/tutor dispatch.

Implementation strategy:

- Integrate existing backend APIs first.
- Focus on frontend contract, no-demo-fallback states, empty/error handling, and role-safe display.
- Add backend work only for missing response fields or contract bugs discovered during integration.

## Candidate v5.5 External Activation Or Native App Buildout

**Status:** Candidate when owner/prerequisite readiness improves

Potential scope:

- Final live payment activation operations once Stripe/TWINT credentials, webhook registration, finance acceptance, and rollout approval are ready.
- Real external support provider and CRM/customer transport activation after approved provider prerequisites are ready.
- Native app implementation, push token integration, app-store release, and mobile offline behavior.

## Candidate v5.6 Curriculum Production Buildout Or Warehouse Deployment

**Status:** Candidate after frontend operations or when content/analytics owners are ready

Potential scope:

- Frontend rich curriculum editor implementation and production content import.
- Live warehouse/BI deployment and scheduled exports if analytics infrastructure ownership is ready.
