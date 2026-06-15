# Next Three Milestones

**Updated:** 2026-06-15 after completing v5.4
**Mode:** product functionality first

## Latest Completed: v5.4 Frontend Learning Operations And Automation Dashboards

**Status:** Completed local frontend release gate 2026-06-15
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Frontend commit:** `/Users/zhdeng/stoa-frontend` `3364a39 feat: add learning operations dashboards`

Goal: make v5.2/v5.3 backend learning operations usable in frontend tutor/admin/student/parent workflows.

Closed scope:

- Added no-demo-fallback frontend learning operations API client, TypeScript contracts, and React Query hooks.
- Added tutor/admin automation review console for preview, refusal review, approved execution, results, and assignment history.
- Added admin/organization learning operations dashboard for analytics, sequencing coverage, quality hotspots, interventions, warehouse readiness, and export summary.
- Added student and parent assignment explanation surfaces without answer keys or internal ranking internals.
- Closed as `frontend-ready`; production frontend deploy/live smoke, native app rollout, live warehouse/BI deployment, and provider activation remain future scope.

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
