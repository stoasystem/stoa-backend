# Phase 7: Weekly Learning Aggregation - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase adds backend weekly learning aggregation for report generation. It should build a deterministic report payload for a linked parent/student/week from real available records: questions, AI answers, teacher help activity, practice progress, mistakes, and weak-topic signals.

</domain>

<decisions>

## Implementation Decisions

### Aggregation Contract

- Add aggregation logic under `src/stoa/services/report_service.py` rather than expanding parent route helpers.
- Build a structured weekly payload that later Bedrock, storage, email, and frontend phases can consume.
- Keep payload deterministic: stable ordering, zero counts for empty data, and no fabricated activity.
- Include parent/student identity metadata, week window, metrics, weak topics, and recent real activity events.

### Data Sources

- Use existing repositories where available: `question_repo`, `practice_repo`, `user_repo`, and DynamoDB table access for conversations/linked children.
- Treat linked student ownership as a required precondition when a parent/student pair is requested.
- Use local DynamoDB `parent_id` and `user_id` identity conventions established in v1.0.

### Time Window

- Accept an explicit week start date and derive the seven-day inclusive/exclusive window.
- Filter by parsed ISO timestamps only; timestamp-free records should not be counted as weekly activity.
- Empty or malformed timestamps should not create fallback activity.

### the agent's Discretion

The agent may choose Pydantic models, dataclasses, or typed dictionaries if the resulting service remains testable and easy for later phases to extend.

</decisions>

<code_context>

## Existing Code Insights

### Reusable Assets

- `src/stoa/routers/parents.py` already contains helper patterns for parsing ISO timestamps, sorting activities, scanning linked children, reading conversations, and calculating current-week parent summary counters.
- `src/stoa/db/repositories/question_repo.py` exposes `list_by_student(student_id, limit, last_key)`.
- `src/stoa/db/repositories/practice_repo.py` exposes `get_progress(student_id)` and `get_mistakes(student_id)`.
- `src/stoa/db/repositories/user_repo.py` exposes local user profile lookup.

### Established Patterns

- Backend services use direct Python functions and dictionaries rather than heavy domain classes.
- DynamoDB records use mixed snake_case and route-level camelCase response conversion.
- Parent identity uses local DynamoDB profile `user_id`, not raw Cognito `sub`.

### Integration Points

- Phase 8 will send the aggregation payload to Bedrock.
- Phase 9 will store report metadata/artifacts derived from the payload.
- Phase 10 will call aggregation for each eligible parent/student/week.
- Phase 11 will eventually expose generated report details through the parent report endpoint.

</code_context>

<specifics>

## Specific Ideas

- Keep the aggregation output compact enough for Bedrock prompt input.
- Include source counts so tests and logs can explain what was aggregated.
- Keep weak-topic ranking frequency-based and deterministic.

</specifics>

<deferred>

## Deferred Ideas

- Bedrock prompt, JSON parser, and fallback generation belong to Phase 8.
- DynamoDB report writes, S3 artifacts, and SES delivery belong to Phase 9.
- Scheduled job orchestration belongs to Phase 10.

</deferred>
