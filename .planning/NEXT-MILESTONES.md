# Next Three Milestones

**Updated:** 2026-06-15 after selecting v5.5
**Mode:** product functionality first

## Latest Completed: v5.4 Frontend Learning Operations And Automation Dashboards

**Status:** Completed local frontend release gate 2026-06-15
**Roadmap archive:** `.planning/milestones/v5.4-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v5.4-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.4-MILESTONE-AUDIT.md`

Goal: make v5.2/v5.3 backend learning operations usable in frontend tutor/admin/student/parent workflows.

Closed scope:

- Added frontend learning operations API client, automation review console, operator dashboard, student/parent assignment explanations, and Open Design e2e evidence.
- Closed as `frontend-ready`; production frontend deploy/live smoke, native apps, live warehouse/BI, live notification delivery, automatic human tutor dispatch, and external provider activation remain future scope.

## Active v5.5 Automatic Teacher Dispatch And SLA Load Balancing

**Status:** Active planning 2026-06-15
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`

Function purpose:

- Automatically route student teacher-help requests to eligible teachers/tutors.
- Reduce request waiting time and SLA breaches.
- Reassign timed-out requests while preserving human replies.
- Give operators visibility into queue age, teacher load, dispatch attempts, and SLA risk.

Implementation strategy:

- Build on existing request-teacher, teacher queue, takeover, reply, resolve, notification, and SLA code.
- Add a dispatch planner, conditional claim/reassignment worker, teacher queue filters, and operator dispatch dashboard.
- Keep live calendar/payroll/native push integrations future scope.

## Candidate v5.6 External Activation Or Native App Buildout

**Status:** Candidate when owner/prerequisite readiness improves

Potential scope:

- Final live payment activation operations once Stripe/TWINT credentials, webhook registration, finance acceptance, and rollout approval are ready.
- Real external support provider and CRM/customer transport activation after approved provider prerequisites are ready.
- Native app implementation, push token integration, app-store release, and mobile offline behavior.

## Candidate v5.7 Curriculum Production Buildout Or Warehouse Deployment

**Status:** Candidate after teacher dispatch or when content/analytics owners are ready

Potential scope:

- Frontend rich curriculum editor implementation and production content import.
- Live warehouse/BI deployment and scheduled exports if analytics infrastructure ownership is ready.
