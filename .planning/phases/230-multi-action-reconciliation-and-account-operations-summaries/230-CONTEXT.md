# Phase 230: Multi-Action Reconciliation And Account Operations Summaries - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend usage reconciliation and usage summaries across governed action types while preserving the existing top-level question quota fields. Parent/admin account operations must receive additive multi-action details without raw content exposure.

</domain>

<decisions>
## Implementation Decisions

### Summary Compatibility
- Preserve `action`, `consumed`, `limit`, `remaining`, and `reconciliation` as question-compatible top-level fields.
- Add `actions`, `groups`, and `totals` for multi-action support explanation.
- Keep non-quota actions support-visible with `limit: null` and `remaining: null`.

### Reconciliation
- Keep question repair behavior unchanged.
- Add read-only action reconciliation for all governed actions.
- Use existing daily counters for chat/hint where counter rows exist.
- Treat support-visible-only actions as `ledger-only` rather than unreconciled.

### Parent/Admin Compatibility
- Add fields to parent/admin usage response models so response filtering does not drop multi-action details.
- Keep account operations payloads additive because they already carry usage as dictionaries.
- Allow admin event listing and reconciliation by action.

### the agent's Discretion
The agent may keep multi-action output compact as long as it explains consumed totals, groups, quota semantics, and reconciliation status.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `USAGE_ACTION_DEFINITIONS` provides action metadata.
- `usage_ledger_repo.list_usage_events` already queries by action/period.
- Parent/admin usage endpoints use Pydantic response models that needed additive fields.

### Established Patterns
- Question reconciliation can repair counters; broader action reconciliation should be read-only.
- Parent/admin account operations treat usage as dict payloads and support warnings read `unreconciled`.

### Integration Points
- `src/stoa/db/repositories/usage_ledger_repo.py`
- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/parents.py`

</code_context>

<specifics>
## Specific Ideas

- Surface grouped totals for `questions`, `chat`, `hints`, `teacher_help`, `practice`, `assignments`, and `generation`.
- Preserve direct question quota UX while adding support-grade explanation for other actions.

</specifics>

<deferred>
## Deferred Ideas

- Frontend rendering polish is deferred unless required by a later UI milestone.

</deferred>
