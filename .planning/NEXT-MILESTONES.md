# Next Three Milestones

**Updated:** 2026-06-15 after completing v5.3
**Mode:** product functionality first

## Latest Completed: v5.3 Controlled Assignment Automation

**Status:** Completed local release gate 2026-06-15
**Roadmap archive:** `.planning/milestones/v5.3-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v5.3-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.3-MILESTONE-AUDIT.md`

Goal: convert v5.2 recommendations into controlled assignment automation from reviewed sources.

Closed scope:

- Defined controlled automation levels, source eligibility, review gates, duplicate rules, delivery states, role visibility, and rollout boundaries.
- Added policy-bounded candidate preview from adaptive sequencing recommendations, accepted AI drafts, curriculum exercises, and assignment outcomes.
- Added approved-batch assignment execution with explicit approval, current-preview binding, deterministic source idempotency, conditional insert, per-item result evidence, and role-safe automation metadata.
- Defined tutor/admin review UX contracts and family-safe student/parent visibility.
- Closed as `automation-ready`; frontend implementation, live notification delivery, native apps, live warehouse/BI, fully unreviewed autonomous tutoring, and external provider activation remain future scope.

## Candidate v5.4 Frontend Learning Operations And Automation Dashboards

**Status:** Recommended next after v5.3

Potential scope:

- Frontend tutor/admin automation review controls for preview, approve, reject, pause/resume, execute, and result history.
- Frontend operator dashboard integration for v5.2/v5.3 analytics and automation controls.
- Student/parent family-safe automated assignment explanations.
- No-demo-fallback handling for automation, analytics, and assignment review states.

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
