---
status: resolved
trigger: "demo teacher账号已经登录，但是学生老师显示没有"
created: 2026-07-09
updated: 2026-07-09
---

# Debug Session: demo-teacher-online-missing

## Symptoms

- expected: When the demo teacher account is logged in, the student UI should show a teacher online/available state.
- actual: Student UI shows German copy "Keine Lehrperson online" and "Lehrpersonen prüfen Anfragen später."
- errors: No technical error shown in the screenshot.
- timeline: Not provided.
- reproduction: Log into the demo teacher account, then view the student-side teacher availability indicator.
- screenshot: /var/folders/13/jgb8c061583ggg622pgv9l0c0000gp/T/codex-clipboard-6b09f854-5d03-461a-a8a2-809d1100b581.png

## Current Focus

- hypothesis: Student chat calls a backend teacher availability endpoint that does not exist, so the UI falls back to an offline state even when a demo teacher is logged in.
- test: Search frontend availability call sites and backend teacher-help routes; add endpoint and focused route/service tests.
- expecting: GET /teacher-help/availability returns online=true when at least one dispatchable teacher profile exists; teacher availability settings persist through /tutors/me/availability.
- next_action: resolved
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-07-09
  observation: Frontend TeacherAvailabilityStatus reads availability.online from useTeacherAvailabilityQuery.
- timestamp: 2026-07-09
  observation: Frontend getTeacherAvailability calls GET /teacher-help/availability.
- timestamp: 2026-07-09
  observation: Backend teacher_help_router only exposed POST /teacher-help/request; GET /teacher-help/availability was missing.
- timestamp: 2026-07-09
  observation: Frontend tutor availability editor calls GET/PATCH /tutors/me/availability, which was also missing from the backend.
- timestamp: 2026-07-09
  observation: Added backend endpoints and tests; focused pytest and ruff checks passed.

## Eliminated

- hypothesis: German copy itself was wrong.
  reason: The copy is selected from frontend state; the state was offline because the backend contract was missing.
- hypothesis: Teacher dispatch planner cannot identify available teachers.
  reason: Existing teacher_dispatch_service already normalizes teacher profile availability and roles; the missing piece was exposing a student-safe availability summary endpoint.

## Resolution

- root_cause: Frontend and backend API contracts were out of sync. Student chat expected GET /teacher-help/availability, and tutor availability UI expected GET/PATCH /tutors/me/availability, but the backend did not implement those routes.
- fix: Added student-safe teacher availability summary, GET /teacher-help/availability, GET/PATCH /tutors/me/availability, and persistence of tutor subjects/weekly availability onto user profiles.
- verification: .venv/bin/python -m pytest tests/test_tutor_availability.py tests/test_conversations.py tests/test_teacher_dispatch.py; .venv/bin/python -m pytest tests/test_ai_teacher_tools.py tests/test_core_smoke.py; .venv/bin/python -m ruff check src/stoa/routers/conversations.py src/stoa/routers/tutors.py src/stoa/services/teacher_dispatch_service.py src/stoa/db/repositories/user_repo.py tests/test_tutor_availability.py
- files_changed: src/stoa/routers/conversations.py, src/stoa/routers/tutors.py, src/stoa/services/teacher_dispatch_service.py, src/stoa/db/repositories/user_repo.py, tests/test_tutor_availability.py
