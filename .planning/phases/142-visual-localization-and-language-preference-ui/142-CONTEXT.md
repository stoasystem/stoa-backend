# Phase 142 Context: Visual Localization And Language Preference UI

## Goal

Expose the v4.1 backend locale preference foundation in the frontend and verify visible English/German localization on a representative authenticated flow.

## Inputs

- Backend locale contract:
  - `PATCH /auth/me/preferences/locale`
  - Body: `{ "preferredLocale": "en" | "de" }`
  - Response: `preferredLocale`, `effectiveLocale`, `supportedLocales`, optional `updatedAt`
  - `/auth/me` exposes `preferredLanguage`, `preferredLocale`, and `effectiveLocale`.
- Frontend workspace: `/Users/zhdeng/stoa-frontend`
- Existing frontend patterns:
  - React/Vite/Tailwind/Radix
  - i18next resources and `LanguageSwitcher`
  - auth store plus React Query current-user loading
  - Playwright e2e tests with demo auth fallback

## Decisions

- Runtime supported languages are narrowed to backend-supported `en` and `de`.
- API canonical values remain language codes; labels remain localized/display-only frontend data.
- Authenticated language changes call the backend locale preference endpoint while unauthenticated changes remain local i18next changes.
- `/auth/me` locale fields drive frontend language state on refresh.
- The login toast was moved from top-right to top-center because it covered right-aligned header controls, including the language switcher.

## Constraints

- French and Italian translation resources may remain in the repository as dormant assets, but the v4.3 runtime selector must expose only English and German.
- Frontend writes and Playwright runs require approval because `/Users/zhdeng/stoa-frontend` is outside the backend writable root.

