# Phase 255 Plan

## Goal

Prove parent, student, and admin journeys work together across the evidence already gathered in v5.16.

## Tasks

1. Map parent journey evidence from frontend e2e and backend account/usage/billing/auth tests.
2. Map student journey evidence from frontend e2e and backend curriculum/question/conversation/usage tests.
3. Map admin journey evidence from frontend e2e and backend account/billing/usage/curriculum/core-smoke tests.
4. Run supplemental frontend e2e for student/teacher-help and parent dashboard paths not included in Phase 253.
5. Identify any journey that relies on hidden production-like demo fallback.
6. Classify residual provider/live-smoke gaps as external-blocked with prerequisites.

## Success Criteria

- Parent, student, and admin journeys have concrete frontend and backend evidence.
- Supplemental student/teacher-help journey e2e passes.
- Demo/mock usage is limited to local e2e fixture behavior and not used as proof of live-provider activation.
- Residual live-provider gaps are explicitly carried to the release gate.
