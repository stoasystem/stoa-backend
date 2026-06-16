# Next Three Milestones

**Updated:** 2026-06-16 after starting v5.6
**Mode:** product functionality first

## Latest Completed: v5.5 Automatic Teacher Dispatch And SLA Load Balancing

**Status:** Completed backend dispatch-ready release gate 2026-06-15
**Roadmap archive:** `.planning/milestones/v5.5-ROADMAP.md`
**Requirements archive:** `.planning/milestones/v5.5-REQUIREMENTS.md`
**Audit:** `.planning/milestones/v5.5-MILESTONE-AUDIT.md`

Goal: automatically route student teacher-help requests to eligible teachers/tutors, reduce waiting time, reassign timed-out requests, and expose queue/SLA health.

Closed scope:

- Added dispatch planner and teacher/tutor candidate ranking.
- Added conditional dispatch claim metadata and stale reassignment behavior.
- Updated request-teacher, teacher queue, takeover, and admin dashboard routes for dispatch state.
- Verified with focused backend tests and Ruff; closed as `dispatch-ready`.
- Live calendar, payroll, native push, frontend dashboard implementation, production scheduled worker wiring, and live production smoke remain future scope.

## Active: v5.6 Native Mobile App And Offline Push Readiness

**Status:** Active planning
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`

Function purpose:

- Make STOA's highest-frequency learning workflows usable from a native mobile client.
- Let students review assignments/progress/reports and track teacher-help status.
- Let parents review child progress/reports and assignment explanations.
- Let teachers/tutors see dispatched help requests and notification-driven workflows.
- Define push/deep-link behavior and offline read-through around existing backend capabilities.

Implementation strategy:

- Reuse v5.0 mobile API/client handoff, v4.9 notification/native delivery readiness, v5.3 assignment automation, v5.4 learning operations UX contracts, and v5.5 teacher dispatch metadata.
- Define app shell, auth/session, role navigation, push-token lifecycle, deep-link payloads, offline cache boundaries, stale indicators, and release gate.
- Keep internal product work moving while treating live APNS/FCM credentials, app-store publication, final live payments, and external support provider activation as separate prerequisites.

Planned scope:

- Phase 201: Native Mobile App And Offline Push Readiness Contract.
- Phase 202: Native App Shell Auth And Role Navigation.
- Phase 203: Native Push Token Deep Link And Notification Delivery.
- Phase 204: Offline Read Through Assignment Report And Help Request UX.
- Phase 205: v5.6 Native Mobile Offline Push Release Gate.

## Candidate v5.7 Frontend Rich Curriculum Editor Or Warehouse Deployment

**Status:** Candidate after v5.6, unless external activation prerequisites unblock

Potential scope:

- Frontend rich curriculum editor implementation from the v5.1/v4.6 authoring readiness work.
- Production source import and migration API/UI if content owners are ready.
- Live warehouse/BI deployment and scheduled exports if analytics infrastructure ownership is ready.
- Broader operator reporting for curriculum quality, assignment outcomes, and dispatch/learning operations.

## Candidate v5.8 External Activation Or Support/Payment Closeout

**Status:** Candidate when owner/prerequisite readiness improves

Potential scope:

- Final live payment activation operations once approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and rollout enablement are available.
- Real external support provider and CRM/customer transport activation after approved provider selection, credentials, destination policy, templates, and rollout approval.
- Production app-store/TestFlight/Play internal testing release after live native provider prerequisites are available.
