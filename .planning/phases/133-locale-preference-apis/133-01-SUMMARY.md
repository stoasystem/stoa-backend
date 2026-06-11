# Phase 133 Summary: Locale Preference APIs

**Phase:** 133
**Status:** Complete
**Completed:** 2026-06-11

## Completed Work

- Added `src/stoa/services/locale_service.py` with supported locales `de`/`en`, default `de`, shared normalization, and effective-locale fallback.
- Added `user_repo.update_locale_preference` to persist locale preference on existing profile records.
- Extended `UserOut` with `preferredLocale` and `effectiveLocale` while preserving `preferredLanguage`.
- Added `PATCH /auth/me/preferences/locale` for authenticated durable locale updates.
- Added focused locale preference tests.

## Decisions

- `de` remains the default when no durable preference exists.
- Regional inputs such as `en-US` and `de_CH` normalize to supported base locales.
- Unsupported locales such as `fr` and malformed locale values are rejected.
- Legacy `language` / `preferredLanguage` fields continue to be read for compatibility.

## Verification

- `.venv/bin/python -m pytest tests/test_locale_preferences.py tests/test_auth_account_lifecycle.py` -> 13 passed.
- `.venv/bin/python -m ruff check src/stoa/services/locale_service.py src/stoa/routers/auth.py src/stoa/db/repositories/user_repo.py tests/test_locale_preferences.py` -> passed.
