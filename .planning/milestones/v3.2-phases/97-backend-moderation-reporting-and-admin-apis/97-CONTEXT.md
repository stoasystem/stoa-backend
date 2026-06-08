# Phase 97 Context: Backend Moderation Reporting And Admin APIs

**Milestone:** v3.2 Content Moderation And Internal Operations
**Requirement:** MOD-02
**Status:** Complete

## Phase Boundary

Implement backend support for moderation case creation and admin moderation operations. Reuse existing question visibility and admin role gates. Store enough context for internal triage without exposing private object keys or expanding into compliance-grade legal workflows.

## Implementation Decisions

- Add moderation request/response models under `stoa.models.moderation`.
- Add a small DynamoDB repository under `stoa.db.repositories.moderation_repo`.
- Keep storage in the existing single table with `PK=MODERATION#<case_id>`, `SK=SUMMARY`, and event rows under `SK=EVENT#...`.
- Use bounded admin scans and in-memory filters for MVP volume.
- Add user report creation at `POST /questions/{question_id}/reports`.
- Add admin list/detail/update/note APIs under `/admin/moderation/cases`.

## Verification Focus

- Student owns-question reporting.
- Teacher/tutor visible-question reporting.
- Invalid target/surface refusal.
- Admin-only list/detail/action APIs.
- Privacy sanity check that image/private S3 keys do not enter API responses.
