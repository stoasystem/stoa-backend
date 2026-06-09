# Phase 105 Summary

## Delivered

- Added `learning_profile_service` with supported subjects, prompt context, topic seed normalization, and learning profile aggregation.
- Updated question submission to normalize supported subjects and store AI-derived topic seed metadata.
- Updated AI prompt construction to include subject-specific context.
- Added `GET /students/{student_id}/learning-profile`.
- Added `GET /parents/me/children/{child_id}/learning-profile`.
- Added focused learning expansion backend tests.

## Code Evidence

- `src/stoa/services/learning_profile_service.py`
- `src/stoa/services/ai_service.py`
- `src/stoa/models/question.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/students.py`
- `src/stoa/routers/parents.py`
- `tests/test_learning_expansion.py`

## Notes

- Existing math question flow remains backward compatible.
- `french` is intentionally rejected because it is not part of the v3.4 contract.
- Learning profile seeds are generated from existing question and practice mistake records.
