---
phase: 123
name: Functional Release Gate And Curriculum Audit
status: complete
created: 2026-06-09
completed: 2026-06-09
requirement: VERIFY-21
---

# Phase 123 Context

## Purpose

Close v3.8 with release-gate evidence for the full curriculum rollout and update the STOA Docs feature gap audit so curriculum is recorded as closed for local functional scope.

## Inputs

- Phase 120 curriculum hierarchy, content lifecycle, lesson/exercise field, and backfill contract.
- Phase 121 backend curriculum catalog, lesson detail, exercise bank, and progress APIs.
- Phase 122 student, parent, and tutor curriculum rollout UI signals.
- `STOA_DOCS_FEATURE_GAP_AUDIT.md` Phase 2 gap tracking.

## Key Boundaries

- v3.8 ships curriculum catalog and exercise bank visibility for math, physics, German, and English using existing practice content/progress records.
- v3.8 does not ship automatic student assignment of generated exercises.
- v3.8 does not ship a long-term adaptive sequencing engine or full rich curriculum authoring workflow.
- Production WebSocket infrastructure, push/native/email notification delivery, payment-provider integration, mobile polish, multilingual polish, and support integrations remain future milestones.
