# Phase 132: Mobile And Multilingual Contract Foundation - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning
**Mode:** Autonomous single-pass discuss

<domain>
## Phase Boundary

Phase 132 defines the backend/client contract for v4.1 before implementation. It must identify mobile-critical flows, establish a supported locale/fallback policy, state what this backend repository can and cannot verify, and update the stale feature gap audit from v4.0 active scope to v4.1 active scope.

This phase is documentation and planning evidence only. It does not add production route behavior; Phase 133 owns durable locale APIs and Phase 134 owns route contract polish.
</domain>

<decisions>
## Implementation Decisions

1. Treat v4.1 as a backend foundation milestone, not a full responsive frontend redesign.
2. Use English and German (`en`, `de`) as the initial supported locale contract because existing registration/profile code already stores `language`/`preferredLanguage`, AI services already pass language hints, and STOA context includes German/English learning support.
3. Store a durable profile preference in Phase 133; do not rely only on JWT/session claims.
4. Keep canonical API values locale-neutral. Localized display labels, if added later, must be separate from IDs, status codes, enum values, timestamps, permissions, and storage keys.
5. Avoid backend user-agent/device sniffing. Mobile readiness means bounded, predictable, client-renderable contracts.
6. Frontend/native mobile layout, touch targets, focus behavior, and visual localization remain deferred unless a UI workspace is added.
</decisions>

<code_context>
## Existing Code Insights

- `src/stoa/routers/auth.py` already accepts `RegisterRequest.preferredLanguage`, stores it as profile field `language`, and returns `UserOut.preferredLanguage` from `language` or `preferredLanguage`.
- `src/stoa/db/repositories/user_repo.py` stores profiles at `PK=USER#{user_id}`, `SK=PROFILE` but does not yet expose a dedicated locale update helper.
- `src/stoa/routers/students.py` exposes student profile, summary, question history, and learning profile routes that are mobile-critical.
- `src/stoa/routers/adaptive.py` exposes memory, recommendation, assignment, and parent progress routes from v4.0 that are mobile-critical.
- `src/stoa/routers/parents.py` exposes parent child list, summary, history, reports, learning profile, subscription, and billing routes.
- `src/stoa/routers/tutors.py` exposes tutor stats, help requests, notes, AI tools, and draft workflows.
- `src/stoa/services/ai_service.py` and `src/stoa/services/learning_profile_service.py` already contain language/subject concepts, but no central locale contract.
</code_context>

<specifics>
## Specific Ideas

- Create a dedicated Phase 132 contract artifact defining mobile-critical flow groups and API responsibilities.
- Update `.planning/research/STOA_DOCS_FEATURE_GAP_AUDIT.md` to mark v4.0 as completed and v4.1 as active.
- Use Phase 132 as the source for Phase 133 implementation: locale normalization, durable profile storage, `/auth/me` exposure, and an authenticated update path.
- Use Phase 132 as the source for Phase 134 implementation: metadata and canonical-value stability tests on selected routes.
</specifics>

<deferred>
## Deferred Ideas

- Responsive frontend layout implementation.
- Native mobile apps.
- Machine translation or translation management.
- RTL visual verification.
- Automatic translation of tutor/student/generated educational content.
</deferred>
