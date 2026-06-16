# Native Mobile App Offline And Push Readiness Contract

## Function Purpose

v5.6 turns STOA's existing backend/frontend readiness into a practical native mobile implementation plan.

The mobile product should let users handle frequent learning workflows without returning to a desktop browser:

- Students review assignments, progress, reports, and teacher-help status.
- Parents review child progress and reports.
- Teachers/tutors see assigned or dispatched help requests.
- Admins/operators view essential learning and dispatch health where mobile access is useful.
- Push notifications open the correct workflow and offline read-through keeps recent read states useful.

## Not This Feature

- Not final live Stripe/TWINT activation.
- Not external support provider or CRM activation.
- Not fully unreviewed autonomous tutoring.
- Not app-store publication unless separate prerequisites are ready.
- Not broad security/compliance hardening unrelated to native mobile functionality.

## Supported Roles And First Screens

| Role | First screen | Core mobile jobs |
|------|--------------|------------------|
| Student | Assignment and progress home | View assigned work, review report/progress, request/track teacher help, open notifications. |
| Parent | Children/progress home | View child progress, report summaries, assignment explanations, notifications. |
| Teacher/Tutor | Dispatched help queue | View dispatched-to-me requests, stale/available requests, reply handoff, SLA state. |
| Admin/Operator | Operations health summary | View learning operations, dispatch/SLA risk, provider-gated notification state. |

## Auth And Session Contract

Native clients should use the existing authenticated API surface or documented Cognito client handoff:

- Login/session establishment through the approved app client flow.
- Session refresh before API calls where token expiry is near.
- Logout clears local tokens, cached role state, and push token association where supported.
- `/auth/me` or equivalent profile call resolves role, locale preference, and available route metadata.

## Mobile API Flow Map

| Mobile flow | Existing foundation | Expected API behavior |
|-------------|---------------------|-----------------------|
| Student assignments | v5.3/v5.4 assignment automation | List/detail with assignment status, source summary, and family-safe explanation metadata. |
| Student progress/report | Parent/student report/progress foundations | Read-only progress and report summary with missing/pending/failed state handling. |
| Teacher help status | v5.5 dispatch metadata | Student sees waiting/assigned/active/replied/resolved only; no ranking internals. |
| Parent child progress | v1.0/v5.4 parent routes and explanation UX | Parent-owned child list/detail/progress/report with no silent demo fallback. |
| Teacher dispatched queue | v5.5 teacher queue filters | Dispatched-to-me, manually available, stale, and no-candidate operator-visible states. |
| Operator dispatch health | v5.5 admin dispatch/SLA metrics | Queue age, assigned load, attempt counts, timeout/reassignment, SLA risk. |
| Notifications | v4.9 notification readiness | List/read/archive/preference behavior compatible with push/deep-link payloads. |

## Push Token Lifecycle

Minimum native token behavior:

1. Client registers token after login with platform, app version, locale, device label, and permission state.
2. Client updates token when provider rotates it.
3. Client unregisters token on logout or app reset.
4. Backend records provider-gated state when APNS/FCM credentials are absent.
5. Notification center remains the fallback source of truth when push delivery is unavailable.

## Notification Event And Deep Link Targets

| Event | Deep link target | Audience |
|-------|------------------|----------|
| `assignment_created` | `stoa://assignments/{assignment_id}` | Student, parent where authorized |
| `assignment_due_soon` | `stoa://assignments/{assignment_id}` | Student |
| `teacher_dispatch_assigned` | `stoa://teacher/requests/{question_id}` | Teacher/tutor |
| `teacher_dispatch_status` | `stoa://questions/{question_id}/teacher-help` | Student |
| `teacher_reply_posted` | `stoa://questions/{question_id}` | Student, parent where authorized |
| `weekly_report_available` | `stoa://reports/{student_id}/{week_start}` | Parent, student where allowed |
| `operator_sla_risk` | `stoa://admin/dispatch` | Admin/operator |

Deep links must degrade to role home when the target is unavailable or unauthorized.

## Offline Read Through Boundaries

Offline read-through is allowed for recently fetched read models:

- Student assignment list/detail.
- Student progress/report summary.
- Parent child progress/report summary.
- Teacher dispatched queue/detail snapshot.
- Notification list and read/archive pending state.

Stale data rules:

- Show `lastSyncedAt`.
- Mark offline/stale state visibly.
- Refresh automatically on reconnect.
- Do not expose internal ranking/refusal details to students or parents from cached operator payloads.

Mutation rules:

- Safe immediate mutations require network confirmation.
- Queue only idempotent mutations with stable request IDs.
- Block teacher replies, assignment completion, and support/payment mutations offline until explicit idempotent contracts exist.

## Ownership

| Area | Owner |
|------|-------|
| Backend API contract and missing mobile metadata | `stoa-backend` |
| Existing web frontend reference flows | `/Users/zhdeng/stoa-frontend` |
| Native app implementation workspace | To be confirmed during Phase 202 |
| Live APNS/FCM credentials and app-store release | External/ops prerequisite |

## Follow-Up Phases

- Phase 202: native app shell auth and role navigation.
- Phase 203: native push token, deep-link, and notification delivery.
- Phase 204: offline read-through assignment, report, and help-request UX.
- Phase 205: release gate, evidence, and next milestone decision.
