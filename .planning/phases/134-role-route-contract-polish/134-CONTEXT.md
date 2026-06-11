# Phase 134: Role Route Contract Polish - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Mode:** Autonomous single-pass discuss

<domain>
## Phase Boundary

Phase 134 applies language-safe metadata and mobile-friendly response checks to selected role-critical backend routes. It should be additive and must not alter canonical IDs, statuses, enum values, timestamps, permissions, or storage keys.
</domain>

<decisions>
## Implementation Decisions

1. Select adaptive learning routes as the first polished role-critical surface because they cover student, parent, tutor, and admin workflows from v4.0.
2. Add a single additive `locale` metadata block rather than localizing canonical values.
3. Include `effectiveLocale`, `contentLanguage`, `supportedLocales`, and `canonicalValuesStable`.
4. Keep parent progress mobile-friendly by preserving existing bounded active/completed assignment slices.
5. Test that `de` and `en` preferences change metadata while canonical memory/recommendation fields remain stable.
</decisions>

<code_context>
## Existing Code Insights

- `adaptive_learning_service.get_memory_summary` powers student/tutor/admin memory responses.
- `adaptive_learning_service.list_assignments` powers student, tutor/admin, and parent assignment lists.
- `adaptive_learning_service.parent_progress_signal` already returns compact active/completed slices capped to five items.
- `adaptive.assignment_response` is shared by tutor/admin create actions and student transitions.
</code_context>

<specifics>
## Specific Ideas

- Add `locale_contract(user)` helper in `adaptive_learning_service`.
- Include locale metadata in memory, recommendation, assignment list, assignment detail/create/transition, and parent progress responses.
- Extend adaptive tests for student, parent, tutor, and admin response metadata.
</specifics>

<deferred>
## Deferred Ideas

- Locale metadata on every admin/report/billing/moderation endpoint.
- Localized display labels for status vocabularies.
- Frontend visual/mobile validation.
</deferred>
