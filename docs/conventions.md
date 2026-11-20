# Conventions

How code in this repository is usually written. Moved from the old `.planning/codebase/CONVENTIONS.md` (#433) after checking each point against the code; the domain vocabulary lives in `CONTEXT.md`, not here.

## Python style and typing

- Ruff is configured in `pyproject.toml` for a 100-character line length and Python 3.12. `ruff check src tests` must pass.
- Imports group standard library, third-party, then `stoa`. Most modules open with a docstring saying what they are for.
- Modern annotations (`str | None`). Pydantic models define most public request and response schemas; a few broad or evolving contracts still use plain `dict` values.
- Repository helpers usually return `dict | None` or `list[dict]`.

## FastAPI and dependencies

- Each route module owns an `APIRouter`; `src/stoa/main.py` is where they are attached.
- Authenticated endpoints use dependencies such as `Depends(get_current_user)` and exact role or capability dependencies, not authentication inside the handler.
- Configuration has two access paths (#359): a service takes `settings` as a parameter, or calls `config.settings()` when it needs a value; routes use `Depends(config.settings)`. Nothing reads configuration at import (except `main.py` building the app). Tests use `config.install(Settings(...))` or pass settings in, never `monkeypatch.setattr` on a settings object; `tests/test_config_access.py` gates this.
- AWS clients come from `stoa.aws.client(Kind.X)` (#358), except DynamoDB, which goes through `stoa.db.table`; tests install doubles with `aws.install` / `db_table.install`.
- The roles are student, parent, teacher and admin (`stoa.models.user.UserRole`). Public registration creates only students and parents; teachers and admins are activated through separate reviewed flows.

## DynamoDB and time

- One table, with `PK`/`SK` values composed by hand. Repositories build keys with `Key`/`Attr` and updates with explicit `UpdateExpression` strings, mapping reserved names through `ExpressionAttributeNames`.
- Query by key or GSI where one exists; some admin aggregates still scan.
- Timestamps are stored as ISO strings in UTC. Tests use injected or frozen clocks.

## Errors and public contracts

- Route validation and authorization failures raise `HTTPException`; provider `ClientError` values are normalized before they reach a client.
- Unknown provider failures become generic dependency failures. Provider codes, payloads, tokens and internal diagnostics never appear in public responses.
- `docs/security/client-error-actions.json` is the checked registry of client actions for HTTP statuses: safe copy, retry policy and correlation-ID handling.
- Non-critical AI or AWS side effects may catch broad exceptions and carry on; tests then assert the side effect and the log, so the branch cannot hide a regression.
- API responses use camelCase for clients; Python internals use snake_case.
- Privacy-sensitive public models use `ConfigDict(extra="forbid", populate_by_name=True)` with explicit camelCase aliases. Attachment responses expose opaque IDs and safe metadata only; practice previews and answer-bearing results are separate allowlisted schemas.
- Active contracts say teacher, never tutor.

## Generated contracts and drift checks

- Route authorization is projected into `docs/security/route-authorization-inventory.json`, client failure behaviour into `docs/security/client-error-actions.json`, and the API into `docs/api/openapi.json`.
- Generators are deterministic. After changing what they read, regenerate and commit, then make sure `scripts/generate_openapi_snapshot.py --check`, `scripts/generate_route_authorization_inventory.py --check` and `scripts/generate_client_error_actions.py --check` pass.
- Generated JSON changes only through its generator, never by hand.

## Mobile (`mobile/`)

- `mobile/tsconfig.json` extends the Expo defaults, enables `strict`, and maps `@/*` to `mobile/src/*`.
- `mobile/app/` follows Expo Router file-based routing. Shared code lives under `mobile/src/`, grouped by `features/`, `services/`, `release/`, `navigation/`, `config/`, `providers/`, `i18n/` and `ui/`.
- Exported data contracts are `type` aliases with discriminated string unions, for example `MobileSession` in `mobile/src/services/auth/authTypes.ts` and `DeepLinkValidation` in `mobile/src/services/notifications/deepLinks.ts`.
- Type-only dependencies use `import type`. Internal imports use the `@/` alias; close siblings use relative imports.
- API modules such as `mobile/src/features/student/studentApi.ts` take the shared client and return endpoint methods. Request adapters translate camelCase fields into the backend's snake_case and encode path values with `encodeURIComponent`.
- Screens are function components using `StyleSheet.create`; providers are composed in `mobile/src/providers/AppProviders.tsx`.
- Routes are declared as explicit arrays in `mobile/src/navigation/routes.ts` (path, label, guard, deep-link flag). Keep them aligned with the screen contracts in `mobile/src/features/*/*Screens.ts` and with `mobile/docs/JOURNEYS.md`.
- Cached reads are typed and TTL-bound (`mobile/src/services/offline/readThroughCache.ts`). Mutations stay server-authoritative and are never replayed offline; TanStack Query allows one query retry and no mutation retries.
- Sign-out clears push registration, query state and secure metadata (`mobile/src/services/auth/signOutCleanup.ts`). Client-visible failures map to support-safe account states (`mobile/src/services/auth/accountState.ts`), never raw provider text.
- `mobile/scripts/validate-mobile-contracts.mjs` is a light static check of required dependencies, the `stoa` scheme, route-group exports and required environment names.

## Repository hygiene

- `.env.example` is tracked; real `.env` files are ignored.
- The repository is LF with `core.autocrlf=false`; Python that writes files passes `newline="\n"`.
