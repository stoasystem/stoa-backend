---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
last_mapped_date: 2026-07-15
---

# Stack

**Mapped:** 2026-07-15
**Scope:** Full repository, incrementally refreshed from `.gitignore`, `.planning`, `docs`, and `mobile`

## Summary

STOA combines a Python 3.12 FastAPI backend with an Expo/React Native mobile workspace. The backend runs locally under Uvicorn and is adapted to AWS Lambda through Mangum. The mobile workspace targets student and parent journeys, but current repository evidence classifies it as a source scaffold rather than a reproducibly buildable client.

The backend exposes role-specific HTTP routes for authentication, student learning, AI conversations, practice lessons, teacher escalation, parent reports, administration, notifications, billing, and file-upload presigning. The active role vocabulary is `student|parent|teacher|admin` as recorded in `.planning/STATE.md`.

## Backend Runtime

- **Language:** Python `>=3.12`, declared in `pyproject.toml`.
- **Application framework:** FastAPI, with the app created in `src/stoa/main.py`.
- **Lambda adapter:** Mangum wraps the FastAPI app as `handler` in `src/stoa/main.py`.
- **Dependency management:** `uv` project metadata in `pyproject.toml`; production lock/export materialized in `requirements.txt` and `uv.lock`.
- **Local development:** The root `README.md` documents `uv` synchronization and Uvicorn startup.

## Backend Core Dependencies

Direct dependencies declared in `pyproject.toml` include:

- `fastapi` for HTTP routing, dependency injection, validation, and OpenAPI.
- `mangum` for AWS Lambda/API Gateway adaptation.
- `pydantic[email]` and `pydantic-settings` for API schemas and environment-backed settings.
- `boto3` for AWS clients and DynamoDB access.
- `python-jose[cryptography]` for Cognito JWT validation.
- `python-multipart` for multipart request compatibility.
- `httpx` for external HTTP, including Cognito JWKS retrieval in `src/stoa/deps.py`.

Development dependencies in `pyproject.toml` include `pytest`, `pytest-asyncio`, `moto`, `ruff`, and `mypy`.

## Mobile Runtime

The native workspace is rooted at `mobile/` and declares its executable stack in `mobile/package.json`:

- Expo SDK 57 with `expo-router` 7 and the `expo-router/entry` main entry point.
- React Native 0.86, React 19.2.3, and strict TypeScript 5.9.
- AWS Amplify 6 plus `@aws-amplify/react-native` for Cognito-compatible authentication.
- TanStack Query 5 for server-state caching and mutation state.
- Expo Notifications, SecureStore, SQLite, Constants, Linking, Splash Screen, and Status Bar.
- i18next/react-i18next for localization and Zustand for client state.

`mobile/tsconfig.json` extends Expo's base configuration, enables strict checking, and maps `@/*` imports to `mobile/src/*`. `mobile/babel.config.js` uses `babel-preset-expo`. File-based routes live under `mobile/app/`; shared code lives under `mobile/src/`.

## Mobile Application and Release Configuration

- `mobile/app.json` defines the Expo app identity, the `stoa` deep-link scheme, iOS and Android package metadata, and plugins for Router, SecureStore, SQLite, and Notifications.
- `mobile/eas.json` defines development, preview, and production build profiles; development and preview use internal distribution.
- `mobile/src/config/mobileConfig.ts` loads the API, Cognito, Expo-project, release-channel, and no-demo-fallback configuration contract without embedding environment values.
- `mobile/src/providers/AppProviders.tsx` supplies a TanStack Query client with bounded query retries and no automatic mutation retries.
- `mobile/src/services/offline/readThroughCache.ts` uses Expo SQLite for privacy-bounded read-through cache records.

The intended stack and release boundary are documented in `mobile/docs/STACK.md`, `mobile/docs/ENVIRONMENT.md`, and `mobile/docs/NATIVE_DISTRIBUTION.md`.

## Application Entry Points

- `src/stoa/main.py` creates the FastAPI app, configures CORS, registers routers, exposes health endpoints, and exports the Lambda handler.
- `src/stoa/config.py` defines backend settings.
- `src/stoa/deps.py` defines shared authentication, authorization, and AWS-client dependencies.
- `mobile/app/_layout.tsx` defines the Expo Router root stack.
- `mobile/app/index.tsx` is the mobile root route.
- `mobile/src/providers/AppProviders.tsx` is the mobile server-state provider boundary.

## Configuration

Backend configuration is centralized in `src/stoa/config.py` through `pydantic-settings`; `.env.example` documents a subset of expected local variables. Configuration families cover environment/CORS, AWS region and resources, Cognito clients, AI-provider limits, usage limits, notifications, billing, WebSocket behavior, and audit controls.

Representative backend setting names include `environment`, `cors_origins`, `aws_region`, `dynamodb_table_name`, `s3_images_bucket`, `s3_reports_bucket`, `s3_presign_expiry_seconds`, Cognito pool/client identifiers, the Bedrock model selector and token limit, daily usage limits, and `teacher_queue_url`. Values are supplied outside this map.

Mobile configuration is centralized in `mobile/src/config/mobileConfig.ts` and typed for development, preview, and production channels. `mobile/docs/ENVIRONMENT.md` specifies that authenticated requests obtain access tokens through Amplify session APIs, push registration crosses backend notification endpoints, offline caching remains read-through only, and sensitive/provider/billing/token material is never cached.

`.gitignore` excludes virtual environments, Python caches, generated distributions, local environment files except `.env.example`, coverage output, and common OS metadata.

## Deployment and Distribution

Backend deployment is defined in `.github/workflows/deploy.yml`: pushes to the main branch run on Ubuntu, install Python 3.12 and `uv`, build an ARM64-compatible Lambda package from `requirements.txt` plus `src/stoa`, assume AWS access through GitHub OIDC, and update Lambda code. Current audit evidence in `docs/audit/full-project-audit.md` reports that this direct deployment path lacks the full verification, staging, immutable-artifact, approval, and rollback gates required for a trustworthy release candidate.

The mobile distribution contract uses EAS profiles in `mobile/eas.json`, with internal development/preview build commands modeled in `mobile/src/release/buildDistribution.ts`. `mobile/docs/NATIVE_DISTRIBUTION.md` explicitly does not claim successful EAS builds, device smoke, or app-store launch.

## Tooling and Verification

- Ruff targets Python 3.12 with a line length of 100.
- Pytest uses the repository `tests` tree and asynchronous test configuration from `pyproject.toml`.
- Mypy is installed as a backend development dependency.
- Mobile scripts in `mobile/package.json` expose Expo start commands, `tsc --noEmit`, and `mobile/scripts/validate-mobile-contracts.mjs`.
- The mobile contract script performs manifest and source-string checks only; `docs/audit/full-project-audit.md` states that it does not import, render, typecheck, call the API, or build native projects.

## Current Stack Constraints

- Lambda packaging targets ARM64, so backend dependencies need compatible wheels or pure-Python distributions.
- The backend assumes externally provisioned AWS resources; the repository audit in `docs/audit/full-project-audit.md` reports no complete executable infrastructure/schema bootstrap in this repository.
- Backend OpenAPI documentation is disabled in the production environment.
- API Gateway buffering constrains the conversation streaming behavior documented in `src/stoa/routers/conversations.py`.
- The mobile dependency matrix is currently unresolvable, no mobile lockfile is checked in, and `mobile/app.json` references a notification asset reported missing by `docs/audit/full-project-audit.md`.
- Most `mobile/app/` routes remain placeholder scaffolds rather than completed student/parent journeys.
- Native build, physical-device, push-delivery, and app-store readiness are not established; `.planning/STATE.md` assigns dependency-matrix repair to Phase 477 and functional mobile integration to Phase 478.
