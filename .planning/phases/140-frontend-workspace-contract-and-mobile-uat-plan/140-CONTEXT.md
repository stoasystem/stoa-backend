# Phase 140 Context: Frontend Workspace Contract And Mobile UAT Plan

## Why This Phase Exists

v4.1 completed backend mobile/multilingual foundations, and v4.3 now needs to implement the visible frontend work. The frontend workspace exists at `/Users/zhdeng/stoa-frontend`; Phase 140 should turn that workspace into an execution-ready mobile and localization plan before UI edits.

## Current Foundation

- Backend exposes durable locale preference support through `/auth/me` and locale preference update APIs.
- Backend route metadata is language-safe and keeps canonical values stable.
- Student, parent, tutor, admin, curriculum, assignment, AI teacher tools, billing, and notification backend surfaces are already available.
- `/Users/zhdeng/stoa-frontend` is a Vite/React workspace with existing `package.json`, `vite.config.ts`, Playwright config, and built assets.

## Phase Boundary

This phase should inspect and document frontend implementation targets. It should not attempt broad redesign before mobile UAT targets and localization strategy are concrete.

## Key Frontend Areas To Inspect

- `/Users/zhdeng/stoa-frontend/package.json`
- `/Users/zhdeng/stoa-frontend/src`
- `/Users/zhdeng/stoa-frontend/src/services` or equivalent API clients
- `/Users/zhdeng/stoa-frontend/src/pages` or route components
- `/Users/zhdeng/stoa-frontend/playwright.config.ts`
- `/Users/zhdeng/stoa-frontend/.planning`

## Constraints

- Current Codex writable workspace is `/Users/zhdeng/stoa-backend`; actual frontend implementation should switch to or receive write approval for `/Users/zhdeng/stoa-frontend`.
- Prioritize feature construction over broad security testing.
- Keep backend canonical values stable; localize display text and labels in frontend code.
- Native mobile app implementation remains out of scope.
