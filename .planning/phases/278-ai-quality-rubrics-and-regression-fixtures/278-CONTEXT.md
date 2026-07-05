# Phase 278: AI Quality Rubrics And Regression Fixtures - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, conservative defaults

<domain>
## Phase Boundary

Define fixtures and scoring rubric before expanding AI behavior.
</domain>

<decisions>
## Implementation Decisions

- Fixtures cover summary, explanation, exercise, assignment, refusal, fallback, and multilingual behavior.
- Rubrics fail unsafe output and low scores.
</decisions>

<code_context>
## Existing Code Insights

AI teacher tools are deterministic local draft helpers today; v5.21 adds evaluation contracts around them.
</code_context>

<specifics>
## Specific Ideas

Add fixture catalog, rubric dimensions, and scoring helper.
</specifics>

<deferred>
## Deferred Ideas

Large fixture corpus can expand after production language and curriculum priorities are approved.
</deferred>
