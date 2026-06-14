# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v5.0 — Native Mobile And Full Localization Governance

**Shipped:** 2026-06-14
**Phases:** 5 | **Plans:** 5 | **Sessions:** 1

### What Was Built

- Native mobile and localization governance contract across backend, frontend/PWA, future native, localization, content, and release ownership.
- Mobile API readiness and client handoff guidance for core role flows, including no-demo-fallback expectations.
- Native notification token lifecycle and offline/read-through state handoff.
- Localization governance, English/German catalog parity evidence, broad copy QA scope, and future-locale/RTL readiness.
- Release gate evidence recording rollout state as `contract-ready`.

### What Worked

- Keeping v5.0 explicitly contract-ready made deferred frontend/native/provider work visible without blocking the milestone.
- Reusing v4.1, v4.3, and v4.9 evidence kept mobile/localization planning aligned with existing backend and frontend foundations.
- The release gate separated backend documentation readiness from frontend-ready, native-ready, and live-activation claims.

### What Was Inefficient

- The archive helper created milestone archives but left several project-level references stale, requiring manual closeout cleanup.
- Summary extraction did not populate top-level milestone accomplishments automatically.
- No phase-level `*-VALIDATION.md` artifacts were produced for this docs-only milestone, leaving Nyquist validation marked as missing.

### Patterns Established

- Use explicit rollout states (`contract-ready`, `frontend-ready`, `native-ready`, `blocked`, `deferred`) for cross-workspace milestones.
- Record frontend/native/provider prerequisites as deferred follow-up work when the current workspace cannot complete them directly.
- Keep mobile client handoff documents tied to route groups, state behavior, fallback rules, and release evidence.

### Key Lessons

1. Cross-workspace milestones need a clear readiness label so documentation contracts do not get mistaken for implemented client releases.
2. Localization governance should distinguish key parity from semantic review, hardcoded-string inventory, and mobile visual QA.
3. Milestone closeout still needs manual inspection after helper automation, especially for `PROJECT.md`, top-level accomplishments, and active-file cleanup.

### Cost Observations

- Model mix: not recorded.
- Sessions: 1 autonomous closeout session.
- Notable: The milestone was documentation-heavy; verification cost centered on artifact traceability and archive hygiene rather than source test runtime.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v5.0 | 1 | 5 | Introduced explicit mobile/localization contract-ready release classification across backend, frontend, native, and localization ownership. |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v5.0 | `git diff --check`; artifact traceability; English/German key parity evidence | Contract coverage for 5/5 requirements | 0 |

### Top Lessons (Verified Across Milestones)

1. Release gates should name the exact rollout state, especially when external credentials, frontend workspaces, or native clients remain out of scope.
2. Archive helpers reduce mechanical work but do not replace a final consistency pass across ROADMAP, REQUIREMENTS, PROJECT, STATE, and MILESTONES.
