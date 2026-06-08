# Moderation Contract: v3.2 MVP

## Reportable Surfaces

| Surface | Reporter Roles | Subject Identifier |
|---------|----------------|--------------------|
| Student question content | student, teacher, tutor, admin | `question_id` |
| AI answer | student, teacher, tutor, admin | `question_id` |
| Teacher reply | student, teacher, tutor, admin | `question_id`, optional `teacher_id` |

## Moderation Case

Minimum fields:

- `case_id`
- `status`: `open`, `in_review`, `actioned`, `dismissed`, `closed`
- `reason`: `incorrect_answer`, `unsafe_content`, `abuse`, `privacy`, `other`
- `severity`: `low`, `medium`, `high`
- `surface`: `question`, `ai_answer`, `teacher_reply`
- `question_id`
- `student_id`
- `reporter_id`
- `reporter_role`
- `assigned_admin_id`
- `report_note`
- `resolution_note`
- `created_at`
- `updated_at`
- `closed_at`
- `history`

## API Shape

User-facing:

- `POST /questions/{question_id}/reports`

Admin:

- `GET /admin/moderation/cases`
- `GET /admin/moderation/cases/{case_id}`
- `PATCH /admin/moderation/cases/{case_id}`
- `POST /admin/moderation/cases/{case_id}/notes`

## Data Access Plan

Preferred DynamoDB shape:

- Case row: `PK=MODERATION#<case_id>`, `SK=SUMMARY`
- Status index mirror fields if existing table GSIs support scan/filter sufficiently for pilot scale.
- History rows: `PK=MODERATION#<case_id>`, `SK=EVENT#<timestamp>#<event_id>`

Phase 97 should first use bounded admin scans for pilot volume unless an existing GSI gives a cleaner status/date query. Do not add new infrastructure for v3.2 unless implementation proves bounded scans are inadequate.

## Functional Verification Priorities

- A student can report their own question.
- A teacher/tutor can report a question visible in their queue/session.
- Admin can list, filter, open, assign, update, note, dismiss, action, and close a case.
- Non-admin users cannot use admin moderation APIs.
- UI supports the full internal workflow with clear empty/loading/error/success states.
