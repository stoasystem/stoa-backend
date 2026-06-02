# Phase 8: Bedrock Report Generation - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>

## Phase Boundary

This phase turns the Phase 7 weekly learning payload into parent-facing generated report content. It owns compact Bedrock input shaping, strict JSON output validation, deterministic fallback content, and parent-safe copy. It does not store reports, send emails, or orchestrate scheduled jobs.

</domain>

<decisions>

## Implementation Decisions

### Generation Contract

- Add report generation helpers to `src/stoa/services/report_service.py` so aggregation and generation remain in one report service for later storage/orchestration phases.
- Build a compact prompt input from the weekly payload: parent/student/week metadata, metrics, top weak topics, and a small bounded activity sample.
- Require generated content to parse as strict JSON with `summary`, `strengths`, `weakTopics`, `recommendations`, and optional `teacherNote`.
- Normalize accepted output into deterministic Python dictionaries with parent-facing field names.

### Fallback Contract

- Bedrock invocation failures, malformed JSON, missing required fields, or unsafe parent-facing copy must return deterministic fallback content.
- Fallback content should use only truthful aggregate metrics and weak-topic names from the weekly payload.
- Empty weekly activity should produce calm no-activity copy, not fabricated learning events.

### Safety Boundary

- Parent-facing generated fields must not include internal provider, model, or implementation terms.
- Logs may include error classes and shape metadata, but should not include full student question content.
- Use existing Bedrock runtime settings and Anthropic Messages payload shape from `src/stoa/services/ai_service.py`.

### the agent's Discretion

The agent may choose exact helper names and tests, provided Phase 9 can consume the returned report content without calling Bedrock again.

</decisions>

<code_context>

## Existing Code Insights

### Reusable Assets

- `src/stoa/services/report_service.py` now produces weekly payloads with parent/student/week, metrics, weak topics, activities, and source counts.
- `src/stoa/services/ai_service.py` shows the established Bedrock runtime pattern: `boto3.client("bedrock-runtime", region_name=settings.aws_region)`, Anthropic Messages JSON body, `settings.bedrock_model_id`, and `settings.bedrock_max_tokens`.
- `tests/test_report_service.py` already monkeypatches repository/table access and can be extended for report generation helpers.

### Established Patterns

- Service helpers use dictionaries and pure functions where possible.
- Tests avoid real AWS clients by monkeypatching dependencies.
- Existing AI output validation checks forbidden internal terms, but tutor parsing is permissive; report generation must be stricter.

### Integration Points

- Phase 9 will persist the generated report content, metadata, and artifacts.
- Phase 10 will call generation for each eligible parent/student/week.
- Phase 11 will expose the generated content to the parent portal.

</code_context>

<specifics>

## Specific Ideas

- `build_bedrock_report_input(payload)` should cap activity and weak-topic lists.
- `parse_generated_report_json(raw_text)` should reject markdown wrappers and partial JSON extraction; strict JSON means the whole string must parse.
- `generate_weekly_report_content(payload, bedrock_client=None)` should accept an injected client for tests.
- The fallback content should return the same shape as accepted generated content.

</specifics>

<deferred>

## Deferred Ideas

- DynamoDB/S3 report persistence belongs to Phase 9.
- SES delivery and delivery failure states belong to Phase 9.
- Idempotent scheduled job orchestration belongs to Phase 10.
- Parent API/frontend rendering belongs to Phase 11.

</deferred>
