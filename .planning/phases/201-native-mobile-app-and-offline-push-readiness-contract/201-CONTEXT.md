# Phase 201 Context: Native Mobile App And Offline Push Readiness Contract

## Milestone

v5.6 Native Mobile App And Offline Push Readiness

## Why This Phase Exists

`stoa_docs` still leaves native mobile apps, mobile push, live notification delivery, and broader product expansion as remaining work. The backend/frontend planning history already closed several prerequisites:

- v5.0: mobile API/client handoff, native notification token and offline-state contracts, localization governance.
- v4.9: notification/native delivery backend readiness and provider-gated push lifecycle records.
- v5.3: controlled assignment automation backend/API readiness.
- v5.4: frontend learning operations dashboards and student/parent assignment explanations.
- v5.5: automatic teacher dispatch metadata, queue filtering, and SLA/load visibility.

The remaining product gap is a coherent native mobile implementation plan that tells client implementers which screens, APIs, push payloads, deep links, and offline behavior to build first.

## Function Purpose

Make STOA usable as a native mobile product for the highest-frequency workflows:

- Students review assignments, progress, reports, and teacher-help status.
- Parents review child progress and reports.
- Teachers/tutors see dispatched help requests and reply workflows.
- Operators/admins view essential learning/dispatch health on mobile where useful.
- Push notifications open the right workflow and degrade safely when live providers are unavailable.

## Implementation Strategy

Phase 201 is a contract phase:

- Define supported roles and first screens.
- Map backend APIs to mobile flows.
- Define push-token lifecycle, notification event types, and deep-link targets.
- Define offline read-through and stale-data behavior.
- Identify ownership between backend, frontend web, and native client workspaces.

## Code Context

Relevant backend areas:

- `src/stoa/routers/auth.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/students.py`
- `src/stoa/routers/teachers.py`
- `src/stoa/routers/notifications.py`
- `src/stoa/routers/admin.py`
- `src/stoa/services/notification_service.py`
- `src/stoa/services/teacher_dispatch_service.py`
- `src/stoa/services/assignment_automation_service.py`

Relevant adjacent workspace:

- `/Users/zhdeng/stoa-frontend` for existing web frontend flows and potential native/web client contract references.

## Planning Boundary

Phase 201 does not publish an app, enable live push credentials, or perform app-store release. Implementation belongs to Phases 202-205.
