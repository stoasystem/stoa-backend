---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
date: 2026-07-15
---

# Conventions

**Mapped:** 2026-07-15
**Scope:** Whole-repository reference, incrementally refreshed from `.gitignore`, `.planning/`, `docs/`, and `mobile/`

## Python Style And Typing

- Backend code follows conventional FastAPI organization: route decorators, route-local request/response models, and centrally attached routers in `src/stoa/main.py`.
- Ruff is configured in `pyproject.toml` for a 100-character line length and Python 3.12.
- Imports generally group standard-library, third-party, and local package imports; module docstrings explain the purpose of most source modules.
- Modern annotations such as `str | None` are preferred. Pydantic models define most public request and response schemas, while a smaller set of broad or evolving contracts still use raw `dict` values.
- Repository helpers conventionally return `dict | None` or `list[dict]`.

## FastAPI And Dependency Patterns

- Each route module owns an `APIRouter`; `src/stoa/main.py` is the composition point.
- Authenticated endpoints use dependencies such as `Depends(get_current_user)` and exact role/capability dependencies rather than handler-local authentication.
- Settings are injected with `Depends(get_settings)` where practical, although some modules still import the cached global from `src/stoa/config.py`.
- Cached AWS factories live in `src/stoa/deps.py`; some services still instantiate `boto3` clients directly, so tests often replace provider boundaries explicitly.
- The current active role vocabulary is student, parent, teacher, and administrator. Public registration is restricted to student and parent; privileged activation follows separate reviewed flows.

## DynamoDB And Time Patterns

- DynamoDB uses manually composed `PK`/`SK` values in a single-table style. Repositories use `Key`/`Attr`, and updates usually build explicit `UpdateExpression` strings.
- Query access is preferred when keys or GSIs exist; administrative aggregate flows may still scan.
- Reserved attribute names are mapped through `ExpressionAttributeNames` where needed.
- Timestamps are ISO strings. New security tests and plans prefer injected or frozen clocks; legacy implementation mixes `datetime.utcnow()` with timezone-aware UTC values.

## Error Handling And Public Contracts

- Route validation and authorization failures use `HTTPException`; provider `ClientError` values are normalized before reaching clients.
- The public identity boundary uses stable, allowlisted error shapes. `docs/security/client-error-actions.json` is the checked client action registry for HTTP statuses, safe copy, retry policy, and correlation-ID handling.
- Unknown provider failures become generic dependency failures; provider codes, payloads, tokens, and internal diagnostics must not appear in public responses or evidence.
- Non-critical AI/AWS side effects may still catch broad exceptions and continue. Tests must assert side effects and logs so these branches do not hide regressions.
- API responses often use camelCase for client compatibility while Python internals and request payload adapters commonly use snake_case.

## Mobile TypeScript And Expo Style

- `mobile/tsconfig.json` extends Expo defaults, enables `strict`, and maps `@/*` to `mobile/src/*`.
- `mobile/app/` follows Expo Router file-based routing. Shared behavior lives under `mobile/src/`, grouped by `features/`, `services/`, `release/`, `navigation/`, `config/`, `providers/`, `i18n/`, and `ui/`.
- Exported data contracts are `type` aliases with discriminated string unions. Examples include `MobileSession` in `mobile/src/services/auth/authTypes.ts` and `DeepLinkValidation` in `mobile/src/services/notifications/deepLinks.ts`.
- Type-only dependencies use `import type`. Internal imports use the `@/` alias; close siblings use relative imports.
- Functions are small named exports or typed factories. API modules such as `mobile/src/features/student/studentApi.ts` and `mobile/src/features/parent/parentApi.ts` accept the shared client and return endpoint methods.
- Boundary values are encoded with `encodeURIComponent`; request adapters translate TypeScript camelCase fields into backend snake_case fields.
- Native screens use function components and `StyleSheet.create`, as in `mobile/src/ui/StateCard.tsx`; provider composition is centralized in `mobile/src/providers/AppProviders.tsx`.
- Immutable contract fixtures use `as const`, for example `mobile/src/i18n/mobileCopy.ts` and release telemetry field allow/deny lists.

## Mobile State And Safety Patterns

- Routes are declared as explicit arrays in `mobile/src/navigation/routes.ts`, with a path, label, guard, and deep-link flag.
- Screen contracts in `mobile/src/features/student/studentScreens.ts` and `mobile/src/features/parent/parentScreens.ts` enumerate endpoint dependencies, supported UI states, offline eligibility, and online-only mutations.
- Cached reads are typed and TTL-bound in `mobile/src/services/offline/readThroughCache.ts`. Mutations remain server-authoritative and are not replayed as offline writes.
- TanStack Query defaults in `mobile/src/providers/AppProviders.tsx` permit one query retry and no mutation retries.
- Authentication uses Amplify wrappers in `mobile/src/services/auth/amplifyAuth.ts`; sign-out clears push registration, query state, and secure metadata through `mobile/src/services/auth/signOutCleanup.ts`.
- `mobile/src/config/mobileConfig.ts` fails fast on required public configuration, strips a trailing API slash, and defaults no-demo-fallback mode to enabled.
- Client-visible failures are mapped into support-safe account states in `mobile/src/services/auth/accountState.ts`; raw provider detail is not used as display copy.
- Deep links are derived from typed targets and revalidated against signed-in, account-ready, and role state in `mobile/src/services/notifications/deepLinks.ts`.

## Contract Generation And Drift Checks

- Route authorization is projected into `docs/security/route-authorization-inventory.json`; client failure behavior is projected into `docs/security/client-error-actions.json`.
- Generators must be deterministic: run generation twice, require byte-identical output, then run `scripts/generate_route_authorization_inventory.py --check` and `scripts/generate_client_error_actions.py --check`.
- Terminology enforcement is semantic, not a raw zero-occurrence search. The checker consumes only exact negative-input or historical-reconciliation exceptions described by `docs/security/tutor-term-allowlist.json`; active contracts use teacher.
- `mobile/scripts/validate-mobile-contracts.mjs` is a lightweight static contract check. It verifies required dependencies, the `stoa` scheme, route-group exports, and required environment names without importing the native application.
- Mobile route and journey declarations should stay aligned across `mobile/src/navigation/routes.ts`, `mobile/src/features/*/*Screens.ts`, and `mobile/docs/JOURNEYS.md`.

## Security Evidence Practice

- Security evidence is source-bound. `docs/security/phase-472-evidence.md` records exact commands, UTC timestamps, result counts, tested source SHA, and deterministic artifact digests.
- Evidence reports focused gates separately from the full-suite observation. A known red baseline is never restated as globally green.
- External checks that were not authorized or configured are recorded as `NOT RUN`, never inferred from local doubles.
- Representative identifiers and outcomes are redacted. Evidence must exclude credentials, raw provider payloads, tokens, private object keys, prompts, answers, transcripts, and billing payloads.
- The evidence record states whether network, provider, AWS, or production mutation occurred and records cleanup/limitations for any approved external operation.
- Cross-phase ownership is explicit: Phase 472 owns its focused authorization regressions, Phase 474 owns deterministic global verification and strict production-configuration fixtures, and Phase 475 owns transaction/atomicity semantics.
- Mobile release evidence applies the same discipline in `mobile/docs/RELEASE_EVIDENCE.md` and the forbidden-field contracts in `mobile/src/release/deviceQa.ts` and `mobile/src/release/releaseTelemetry.ts`.

## GSD Planning Artifacts

- `.planning/config.json` enables source-grounded plan review, plan checking, verification, and Nyquist validation; automatic phase advance is disabled.
- A phase directory conventionally contains `*-CONTEXT.md`, one or more `*-PLAN.md` files, task `*-SUMMARY.md` files, `*-VALIDATION.md`, and `*-VERIFICATION.md`. Review-heavy phases may also contain `*-RESEARCH.md`, `*-PATTERNS.md`, `*-REVIEW.md`, and a discussion log.
- Plans define scope, threats, requirements, commands, evidence, and cross-phase deferrals before implementation. Summaries record actual changes, commands, deviations, and remaining ownership.
- Validation maps each task to a requirement, test type, command, file-existence state, and status. Verification independently inspects source and reruns evidence before marking the phase passed.
- Planning documents use concrete backticked paths and preserve historical observations rather than rewriting earlier evidence to match a later run.

## Repository Hygiene

- `.gitignore` excludes virtual environments, Python caches, local environment files, build output, Ruff/mypy/pytest caches, coverage HTML, package metadata, and macOS metadata.
- `.env.example` is intentionally trackable; real `.env` variants are ignored.
- Generated security JSON is committed evidence and should change only through its deterministic generator/check workflow.
