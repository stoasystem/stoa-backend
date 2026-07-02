# Next Three Milestones

**Updated:** 2026-07-02 after correcting v5.6
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

## Active: v5.6 Core Product Operations Completion

**Status:** Active planning
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`

Function purpose:

- Complete real-user product details before native app work.
- Make paid entitlement state reliable and visible.
- Record user/student usage in a durable backend ledger.
- Complete email verification and login verification-code policy.
- Expose customer/admin billing, usage, verification, and support state.

Implementation strategy:

- Audit existing auth, subscription, billing, quota, usage, verification, and admin code paths.
- Build deterministic effective entitlement from subscription tier, billing provider state, manual overrides, rollout controls, cancellation/expiry, and pending payment.
- Add a usage ledger for plan-governed actions such as question submission, OCR/AI usage, and teacher-help requests.
- Complete verification-code lifecycle with expiry, resend, attempt limits, and account-state effects.
- Keep native apps, live APNS/FCM, app-store release, and external support activation as later milestones.

Planned scope:

- Phase 201: Core Product Operations Gap Audit And Contract.
- Phase 202: Paid Entitlements And Usage Ledger.
- Phase 203: Email Verification And Login Code Completion.
- Phase 204: Customer And Admin Billing Usage Visibility.
- Phase 205: v5.6 Core Product Operations Release Gate.

## Candidate v5.7 Frontend Rich Curriculum Editor Or Native App Buildout

**Status:** Candidate after v5.6, depending on core operations completion and owner readiness

Potential scope:

- Frontend rich curriculum editor implementation from the v5.1/v4.6 authoring readiness work.
- Native iOS/Android app buildout once account/payment/usage correctness is reliable.
- Production source import and migration API/UI if content owners are ready.
- Live warehouse/BI deployment and scheduled exports if analytics infrastructure ownership is ready.

## Candidate v5.8 External Activation Or Support/Payment Closeout

**Status:** Candidate when owner/prerequisite readiness improves

Potential scope:

- Final live payment activation once approved live Stripe credentials, registered production webhook endpoint, TWINT capability approval, finance acceptance, and rollout enablement are available.
- Real external support provider and CRM/customer transport activation after approved provider selection, credentials, destination policy, templates, and rollout approval.
- Production app-store/TestFlight/Play internal testing release after native and provider prerequisites are available.
