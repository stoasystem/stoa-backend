# Phase 267: Native Mobile Stack And App Shell Contract - Context

**Gathered:** 2026-07-06
**Status:** Ready for planning
**Mode:** Autonomous smart discuss, accepted conservative defaults

<domain>
## Phase Boundary

Scaffold a native Expo mobile client inside this repository so v5.19 can execute against versioned code and release evidence. This phase covers stack declaration, route shell, environment contract, no-demo-fallback policy, and static verification only.
</domain>

<decisions>
## Implementation Decisions

- Create `mobile/` in the backend repository because the current writable workspace is `/Users/zhdeng/stoa-backend`.
- Use Expo SDK 57, React Native 0.86, React 19.2, Expo Router, Amplify Auth, Expo Notifications, SecureStore, SQLite, and TanStack Query.
- Do not install mobile dependencies during this phase; local verification remains static because network/package install is not guaranteed.
- Keep app-store launch and live device push credentials out of scope.
- Keep all authenticated mobile surfaces no-demo-fallback by default.
</decisions>

<code_context>
## Existing Code Insights

Backend notification, parent, practice, question, auth, entitlement, usage, and account-operation routes already exist. The mobile client should consume those contracts rather than create a parallel product model.
</code_context>

<specifics>
## Specific Ideas

- Add `mobile/package.json`, `app.json`, `eas.json`, `tsconfig.json`, route files, provider shell, UI scaffold, config contract, and docs.
- Add Python tests that statically validate the stack and route/environment contracts from the backend test suite.
</specifics>

<deferred>
## Deferred Ideas

- Auth wiring, API adapters, push handling, offline cache implementation, and release gate evidence happen in later phases.
</deferred>
