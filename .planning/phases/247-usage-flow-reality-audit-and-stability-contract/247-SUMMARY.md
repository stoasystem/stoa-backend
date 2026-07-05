# Phase 247 Summary

## Status

Complete.

## Completed

- Mapped usage-bearing backend flows to route/service files and test evidence.
- Mapped reachable frontend usage entry points and support explanation surfaces.
- Classified flows as counter plus ledger, ledger-only, intentionally skipped, missing, future-only, or externally blocked.
- Documented consume and skip rules for failed requests, read-only flows, duplicate question retries, previews/dry-runs, and provider-blocked paths.
- Derived concrete Phase 248-250 work from the audit instead of expanding BI/APM scope.

## Key Findings

- Existing coverage is strongest for question submit, chat message, hint request, teacher-help requests, practice answer, lesson completion, and assignment lifecycle events.
- Practice teacher-help is a real route/frontend API but currently has no usage ledger event.
- Question, chat, and hint flows need partial-failure/idempotency tests around counter and ledger ordering.
- Rate-limit counters can show over-limit drift when a request increments before rejection; reconciliation should classify this explicitly.
- Account operations already have support-safe usage visibility, but Phase 249 should sharpen explanations and recommended support action.

## Next Phase

Phase 248 Ledger Coverage And Idempotency Closure should close practice teacher-help coverage and add tests for duplicate/partial-failure behavior without changing privacy boundaries.
