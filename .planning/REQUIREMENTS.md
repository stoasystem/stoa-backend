# Requirements: v3.1 Teacher Reply Quality And SLA Operations

**Milestone:** v3.1
**Status:** Active
**Created:** 2026-06-08

## Goal

Close the remaining teacher-takeover MVP gaps from `stoa_docs`: rich text/formula reply contract, response-time SLA tracking, teacher/admin visibility, and release verification without expanding into broad Phase 2 payments or multi-subject scope.

## Requirements

### TEACHOPS-01 Teacher Reply And SLA Contract Readiness

Implementers have a precise teacher reply content contract, SLA event model, privacy boundary, and verification plan before changing teacher reply behavior.

Acceptance criteria:

- Contract defines allowed rich text/formula input shape, safe rendering/output shape, markdown/HTML/LaTeX handling, validation limits, and refusal behavior.
- Contract defines teacher-request, queue-visible, takeover, first-reply, resolve, and timeout SLA timestamps.
- Contract defines SLA metrics for teacher queue, admin stats, and future compensation/operations reporting without exposing private student content.
- Privacy model forbids leaking private image keys, report artifact keys, presigned URLs, auth tokens, cookies, passwords, AWS secrets, or raw unsafe HTML.
- CDK/infrastructure readiness confirms no new resource is needed, or records any exact required change.

### TEACHOPS-02 Backend Rich Reply Metadata And SLA Tracking

Backend teacher takeover records safe rich reply metadata and SLA timing evidence.

Acceptance criteria:

- Teacher reply API accepts the approved rich reply/formula payload and stores sanitized metadata.
- Backend records request-to-takeover, request-to-first-reply, takeover-to-first-reply, and resolve timing where data exists.
- Admin stats or teacher stats expose aggregate SLA metrics without private question content.
- Tests cover validation, sanitization, formula payloads, stale/invalid state, authorization, and SLA calculations.

### UI-16 Teacher Reply Composer And SLA Visibility

Teacher and admin UI make rich replies and SLA state visible without unsafe content rendering.

Acceptance criteria:

- Teacher reply composer supports the approved rich text/formula contract.
- Teacher queue/session UI shows SLA status and timing indicators.
- Admin stats/reporting exposes aggregate teacher response metrics.
- Playwright covers rich reply render, formula-safe display, SLA status, admin gating, and private marker denial.

### VERIFY-14 v3.1 Release Gate And STOA Docs Alignment

v3.1 closes with test/deploy/live-smoke evidence and updated `stoa_docs` gap audit.

Acceptance criteria:

- Backend/frontend quality gates, deploy evidence, commit SHAs, timestamps, production API request IDs, and browser smoke are recorded.
- Feature gap audit marks teacher rich reply and SLA tracking outcomes accurately.
- Production smoke avoids customer content mutation unless a named non-customer safe fixture and cleanup path are documented.
- Final audit records residual gaps, including content moderation and Phase 2 expansion.

## Future Requirements

- Content moderation workflow for reported/unsafe content.
- Stripe/TWINT subscription payments.
- Broad multi-subject rollout for physics, German, and English.
- Student memory/personalization.
- AI teacher assistance tools such as summaries and exercise generation.
- WebSocket realtime notifications.
- Mobile responsive polish and full multilingual rollout.
- Real user email verification policy change if product/legal requires it.

## Out of Scope

- Stripe/TWINT billing implementation.
- Broad multi-subject curriculum/content rollout.
- Direct production customer content mutation without an approved safe fixture.
- Unsafe raw HTML rendering.
- Direct support-system writes.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TEACHOPS-01 | Phase 92 | Complete |
| TEACHOPS-02 | Phase 93 | Complete |
| UI-16 | Phase 94 | Planned |
| VERIFY-14 | Phase 95 | Planned |
