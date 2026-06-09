# Phase 117 Summary: Backend Teacher Summary And Exercise Draft APIs

Status: complete
Completed: 2026-06-09

## Implementation

- Added `ai_teacher_draft` DynamoDB repository helpers for put/get/list/update.
- Added `ai_teacher_tools_service` for reviewed summary and practice exercise draft generation.
- Added tutor/admin routes under `/tutors/ai-tools` and `/tutors/questions/{question_id}/ai-tools/summary-draft`.
- Added draft lifecycle endpoints for regenerate, accept, reject, and archive.
- Added focused backend tests covering visibility authorization, generation shape, topic binding, lifecycle, and the no-student-delivery boundary.

## Verification

- `PYTHONPATH=src .venv/bin/pytest tests/test_ai_teacher_tools.py tests/test_notifications.py tests/test_teacher_reply_sla.py` - passed, 18 tests.
- `.venv/bin/ruff check src/stoa/db/repositories/ai_teacher_tools_repo.py src/stoa/services/ai_teacher_tools_service.py src/stoa/routers/tutors.py tests/test_ai_teacher_tools.py` - passed.

## Notes

- Generation is deterministic and context-derived in this phase for local safety and testability.
- Generated summaries and exercises persist as reviewed drafts; `studentDeliveryStatus` remains `not_delivered`.
- Future Bedrock prompt tuning can replace the generator without changing API or lifecycle contracts.
