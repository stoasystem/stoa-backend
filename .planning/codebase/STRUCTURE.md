---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
last_mapped_date: 2026-07-15
---

# Structure

**Mapped:** 2026-07-15
**Scope:** Full repository

## Top-Level Layout

- `README.md` — concise project overview, local setup, stack, and source layout.
- `pyproject.toml` — package metadata, direct dependencies, optional dev dependencies, Ruff and Pytest config.
- `requirements.txt` — production requirements exported by `uv`.
- `uv.lock` — lockfile for Python dependencies.
- `.env.example` — local environment variable template.
- `.github/workflows/deploy.yml` — production Lambda deployment workflow.
- `.gitignore` — excludes local Python environments/caches, environment files, build output, coverage, and editor/OS artifacts while retaining `.env.example`.
- `.planning/` — versioned project state, roadmap, milestone/phase workspaces, research, debug records, and codebase maps.
- `docs/` — checked audit and generated security evidence.
- `mobile/` — independent Expo/React Native client package for student and parent native journeys.
- `scripts/seed_practice.py` — DynamoDB seed script for ZAP Langgymnasium Zürich practice content.
- `src/stoa/` — Python package for the FastAPI backend.

## Source Package Layout

`src/stoa/` contains:

- `main.py` — app composition and Lambda handler.
- `config.py` — settings model and cached settings accessor.
- `deps.py` — FastAPI dependencies, auth validation, role guards, and AWS client factories.
- `routers/` — HTTP route modules.
- `models/` — shared Pydantic models.
- `services/` — AI/OCR/notification/rate-limit service helpers.
- `db/` — DynamoDB table wrapper and repository helpers.

## Routers

`src/stoa/routers/auth.py`

- Cognito registration, login, refresh, logout, and `/me`.
- Contains route-local request/response models.
- Rejects public privilege creation; teacher onboarding uses the separate approved lifecycle.

`src/stoa/routers/conversations.py`

- Student AI conversation list/detail/create/send/stream.
- Conversation teacher-help request router.
- Contains direct DynamoDB helper functions and route-local Pydantic models.

`src/stoa/routers/practice.py`

- Practice subjects, overview, roadmaps, paths, lessons, challenge answers, mistakes, hints, and teacher-help placeholder.
- Contains response builder helpers for frontend contract shaping.

`src/stoa/routers/questions.py`

- One-off question submission, question retrieval, teacher escalation, and feedback.
- Uses question repository, user repository, OCR service, AI service, and notification service.

`src/stoa/routers/students.py`

- Student profile get/update.
- Student summary and question history.
- Resolves profiles by direct DynamoDB lookup or Cognito email lookup.

`src/stoa/routers/teachers.py`

- Escalated question queue, takeover, reply, and resolve endpoints.
- Persists teacher sessions directly in DynamoDB.

`src/stoa/routers/parents.py`

- Parent child listing and weekly report lookup.
- Uses direct DynamoDB scan for child lookup and report repository for reports.

`src/stoa/routers/admin.py`

- Admin user listing, user update, and platform stats.
- Uses full-table scans for aggregate metrics.

`src/stoa/routers/files.py`

- S3 presigned PUT URL endpoint for direct image uploads.

## Models

`src/stoa/models/question.py`

- `QuestionStatus`
- `AIResponse`
- `SubmitQuestionRequest`
- `QuestionResponse`
- `FeedbackRequest`

`src/stoa/models/report.py`

- `WeeklyReportResponse`

`src/stoa/models/user.py`

- User-related enums and schemas; imported by admin routes for `SubscriptionTier`.

Many route modules define additional local request/response schemas close to the endpoint that uses them.

## Database Helpers

`src/stoa/db/dynamodb.py`

- Cached DynamoDB table accessor.

`src/stoa/db/repositories/user_repo.py`

- `put_user`
- `get_user`
- `get_user_by_email`

`src/stoa/db/repositories/question_repo.py`

- `put_question`
- `get_question`
- `list_by_student`
- `update_status`

`src/stoa/db/repositories/practice_repo.py`

- Practice content reads for subjects, topics, units, lessons, and challenges.
- Student progress and mistake writes/reads.

`src/stoa/db/repositories/report_repo.py`

- Weekly report put and GSI lookup by parent/week.

## Services

`src/stoa/services/ai_service.py`

- Bedrock AI learning-assistance prompt harness.
- Prompt injection sanitization.
- JSON parsing and output validation.
- Main answer generation and hint generation.

`src/stoa/services/ocr_service.py`

- Rekognition text extraction from S3 objects.

`src/stoa/services/notify_service.py`

- SQS teacher escalation enqueue.
- SES weekly report email send.

`src/stoa/services/rate_limit.py`

- DynamoDB atomic daily counters for chat messages and practice hints.

## Security Contracts

`src/stoa/security/`

- Immutable canonical Actor, account-status, and capability-grant contracts.
- Typed resource/action/purpose authorization inputs and repository protocols.
- Stable safe error taxonomy, allowlisted security-event projection, and generated client recovery actions.
- `public_auth_errors.py` is the closed operation-aware boundary for redacted public identity-provider failures.
- Phase 472 implements policy evaluation, token verification, route inventory, onboarding, reconciliation, and evidence-before-effect authorization.

## Mobile Workspace

`mobile/package.json`

- Independent private package with runtime entry `expo-router/entry`.
- Expo start targets and focused `typecheck` / `test:contracts` validation scripts.

`mobile/app/`

- Expo Router filesystem entry points.
- `_layout.tsx` is the root stack/provider composition boundary; `index.tsx` redirects to sign-in.
- `auth/` contains sign-in, registration, and email-verification entries.
- `student/` contains dashboard, practice, questions, and history entries.
- `parent/` contains dashboard, billing, and dynamic child summary/history/report entries.
- `notifications/` contains notification list and dynamic event detail entries.
- `blocked/` contains verification, entitlement, and provider-unavailable account-state entries.

`mobile/src/features/`

- Role-oriented API adapters and screen-state builders in `student/` and `parent/`.
- API paths are backend contracts; authenticated journeys do not embed demo responses or fixture user IDs.

`mobile/src/services/`

- `api/` — one authenticated fetch wrapper and structured mobile API error.
- `auth/` — Amplify/Cognito setup, session restore, account-state mapping, metadata-only secure persistence, and sign-out cleanup.
- `journeys/` — shared loading/ready/empty/blocked/stale/error state contract.
- `notifications/` — backend notification adapters, Expo push registration, payload types, and role-aware deep-link validation.
- `offline/` — allowlisted read-through cache policy and SQLite helpers; sensitive and mutation data remains online-only.

`mobile/src/navigation/routes.ts`

- Central route, role-guard, and deep-link inventory for public, student, parent, authenticated, and blocked surfaces.

`mobile/src/config/mobileConfig.ts`

- Required public API/Cognito coordinates, optional Expo project ID, release channel, and no-demo-fallback assertion.

`mobile/src/providers/` and `mobile/src/ui/`

- Root TanStack Query provider plus shared screen/state primitives.

`mobile/src/release/`

- Source contracts for build distribution, credential readiness, device QA, telemetry, and store readiness; these describe gates and evidence without embedding credentials.

`mobile/docs/`

- Maintainer contracts for stack, environment, authentication, journeys, push/offline behavior, native distribution, and release evidence.

`mobile/scripts/validate-mobile-contracts.mjs`

- Static package, route-group, deep-link scheme, dependency, and public environment-name checks.

## Planning Workspace

`.planning/` top-level control files:

- `PROJECT.md` — product/project definition.
- `REQUIREMENTS.md` — active requirement registry.
- `ROADMAP.md` — active milestone phase order and release boundary.
- `STATE.md` — current execution state, decisions, blockers, and next actions.
- `MILESTONES.md`, `NEXT-MILESTONES.md`, and `RETROSPECTIVE.md` — milestone history and sequencing.
- `config.json` — local GSD workflow configuration.

Planning subtrees:

- `.planning/milestones/` — archived version-specific roadmaps, requirements, audits, and phase evidence.
- `.planning/phases/<number>-<kebab-case-slug>/` — active or retained phase workspaces.
- `.planning/codebase/` — seven whole-repository maps (`ARCHITECTURE.md`, `STRUCTURE.md`, `STACK.md`, `INTEGRATIONS.md`, `CONVENTIONS.md`, `TESTING.md`, and `CONCERNS.md`).
- `.planning/research/` — cross-cutting architecture, stack, feature, pitfall, and gap research.
- `.planning/debug/` — focused diagnostic records, including resolved operational failures.
- `.planning/ui-reviews/` — ignored-output holding directory retained by its local `.gitignore`.

Phase file naming is deliberately sortable: `<phase>-<plan>-PLAN.md` pairs with `<phase>-<plan>-SUMMARY.md`; shared phase records use `<phase>-CONTEXT.md`, `<phase>-RESEARCH.md`, `<phase>-VALIDATION.md`, `<phase>-VERIFICATION.md`, and `<phase>-REVIEW.md`. Domain-specific evidence adds explicit suffixes such as `-AUDIT.md`, `-RUNBOOK.md`, `-RELEASE-GATE.md`, or `-EVIDENCE-LEDGER.md`.

## Audit And Generated Documentation

`docs/audit/`

- `full-project-audit.md` is the narrative audit.
- `findings.json` is the machine-readable finding registry and audit provenance.

`docs/security/`

- `route-authorization-inventory.json` is the generated registered-route authorization projection.
- `client-error-actions.json` is the generated safe client recovery-action contract.
- `phase-472-evidence.md` records source-bound local verification, deterministic hashes, and explicit unavailable-live-evidence boundaries.
- `tutor-term-allowlist.json` contains only rejected historical terminology exemptions for the canonical `teacher` terminology gate.

Generated JSON is checked into the repository so deterministic `--check` jobs can detect drift between executable route/security metadata and review artifacts. Security documentation must remain redacted and must not record secrets, tokens, raw provider payloads, or private object keys.

## Scripts

`scripts/seed_practice.py`

- Seeds mathematics practice content for ZAP Langgymnasium Zürich.
- Writes subject/topic/unit/lesson/challenge records to DynamoDB.
- Content is structured as Python data factory functions.

## Naming Conventions

- Python modules use snake_case.
- API responses often use frontend-facing camelCase, especially in route-local Pydantic models and response dictionaries.
- DynamoDB keys use uppercase entity prefixes: `USER#`, `QUESTION#`, `PRACTICE`, `CONV#`, `PROGRESS#`, `MISTAKES#`, `USAGE#`, `SESSION#`.
- `teacher` is the sole active role/API term; the older label is confined to rejected historical evidence and its exact allowlist.
- Mobile route files follow Expo Router conventions: directory segments become paths, `[childId].tsx` and `[eventId].tsx` are dynamic segments, and `_layout.tsx` is a composition boundary.
- Planning phase directories use a numeric prefix plus kebab-case slug; plan/evidence files repeat the phase number for lexical grouping.
- Generated security JSON uses stable schema fields and deterministic ordering so checked artifacts can be regenerated byte-for-byte.

## Missing or Sparse Areas

- No infrastructure-as-code directory exists in the repository.
- No explicit OpenAPI contract artifact exists outside FastAPI route definitions.
- `mobile/` declares its native dependency matrix but has no committed package-manager lockfile; its own release evidence treats dependency installation, EAS credentials/builds, physical-device QA, and store launch as separate gates.
