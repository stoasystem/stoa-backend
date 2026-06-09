# Phase 117 Context: Backend Teacher Summary And Exercise Draft APIs

## Decision Summary

User delegated implementation decisions. Build backend tutor/admin AI teacher tool draft APIs as reviewed draft workflows, not student delivery workflows. Reuse existing question, learning profile, teacher assistance, and single-table DynamoDB patterns.

## Existing Code Context

- `tutors.py` already exposes tutor/admin help request and assistance summary routes.
- `teacher_assistance_service.py` already builds bounded summary seeds from visible question context.
- `learning_profile_service.py` provides supported subjects, topic normalization, and profile seed aggregation.
- `question_repo.py` provides question lookup and student question listing.
- Existing v3.7 Phase 116 contract defines no-auto-send and reviewed lifecycle boundaries.

## Implementation Decisions

- Add a dedicated `ai_teacher_draft` entity/repository for generated summary and exercise drafts.
- Add tutor/admin routes under `/tutors/ai-tools`.
- Treat both `teacher` and `tutor` roles as tutor workflows; admins can inspect broader scope.
- Summary draft generation requires visible question context.
- Exercise draft generation requires subject/topic/student context; tutors need visible evidence for that student unless generating from an explicitly visible question.
- Generate deterministic local draft content from available context for safety and testability. Future Bedrock prompt integration can replace the generator without changing persistence or lifecycle contract.
- Persist lifecycle metadata: `status`, `created_by`, `source_context`, `prompt_version`, `generated_at`, `reviewed_by`, `reviewed_at`, `review_note`, and previous draft linkage for regeneration.

## Deferred

- Automatic assignment or student delivery of generated exercises.
- Full curriculum-aligned exercise banks.
- Production prompt/model tuning beyond the stable service contract.
