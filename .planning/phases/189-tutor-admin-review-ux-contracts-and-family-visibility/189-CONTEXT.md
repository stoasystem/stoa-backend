# Phase 189 Context: Tutor Admin Review UX Contracts And Family Visibility

## Milestone

v5.3 Controlled Assignment Automation

## Requirement

AUTOASSIGN-04 Tutor/Admin Review UX Contracts And Family Visibility

## Inputs

- Phase 186 controlled automation contract.
- Phase 187 preview endpoint and selected/refused candidate response shape.
- Phase 188 execution endpoint, deterministic source idempotency, automation metadata, and role-safe assignment response.
- Existing adaptive route locale contract and parent progress route.

## Constraints

- This repository does not contain the frontend app; deliver a backend-verified frontend/API handoff contract.
- Parent/student explanations must not expose answer keys, raw ranking internals, hidden source signals, or private tutor-only evidence.
- Fully unreviewed automatic tutoring and live push/notification delivery remain out of scope.
- Canonical API values must remain locale-neutral; UI copy can localize display labels later.

## Desired Outcome

Frontend and operator implementation teams have a concrete contract for preview, approve, reject, override, pause/resume, result history, intervention views, empty states, and family-safe automated assignment explanations.
