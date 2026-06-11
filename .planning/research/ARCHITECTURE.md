# v4.1 Architecture Research: Mobile And Multilingual Polish Foundation

**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Researched:** 2026-06-11

## Architectural Position

The backend should act as the contract and preference authority, while clients own responsive layout, touch ergonomics, and locale-sensitive rendering. v4.1 should add small shared services rather than one-off locale logic in every router.

## Proposed Components

### Locale Preference Service

Responsibilities:

- Normalize requested locale values.
- Enforce supported locale allowlist and fallback.
- Store preferences on durable profile/user records.
- Return current effective locale for authenticated users.
- Keep default behavior stable for existing users.

Candidate module shape:

- `locale_service.py` or a small helper inside the existing profile service boundary.
- Repository helpers for reading/writing profile preference fields.
- Pydantic request/response models such as `LocalePreferenceUpdate` and `LocalePreferenceResponse`.

### API Contract Metadata

Responses that expose language-sensitive content should carry explicit metadata where useful:

- `locale` or `language` for display strings.
- Per-content `language` metadata where educational material already has subject/language context.
- Canonical `status`, `id`, `type`, and timestamps unchanged across locale.
- Optional `display` fields separated from canonical data.

This avoids clients inferring language from free-form text and prevents translated labels from becoming API state.

### Mobile-Friendly Route Patterns

Use route contracts instead of backend device detection:

- List endpoints should remain bounded and pageable.
- Heavy detail fields should stay in detail endpoints where feasible.
- Parent/student/tutor overview routes should expose summary fields that clients can render in compact mobile surfaces.
- Error responses should be consistent enough for mobile clients to show concise retry states.

### Role Integration Points

Likely integration areas:

- Auth/current-user profile response: expose locale preference.
- Student profile/preferences route: allow self-service locale changes where appropriate.
- Parent-facing profile or child overview routes: expose effective locale metadata without weakening authorization.
- Tutor/admin routes: preserve operational canonical values and add display metadata only when needed.
- Learning profile/curriculum services: preserve existing subject language metadata and align it with the new locale vocabulary.

## Data Model Guidance

Suggested profile fields:

- `preferred_locale`: normalized locale tag, initially `en` or `de`.
- `locale_updated_at`: ISO timestamp for audit/debug value.
- Optional future fields: `content_language`, `timezone`, `text_direction`.

Do not store:

- Browser user-agent derived device class.
- Translated copies of canonical status values.
- Locale only in temporary access tokens.
- Unbounded per-string translation maps in profile records.

## Testing Architecture

Core tests:

- Supported locale accepted.
- Unsupported locale rejected or falls back according to the chosen contract.
- Missing locale returns deterministic default.
- Existing users without locale continue to pass.
- Canonical response fields do not change under different locale preferences.
- Authorization tests remain unchanged for every route that receives locale support.

Contract tests:

- Profile response includes effective locale.
- Locale update persists to repository.
- Role-critical responses either include expected language metadata or are documented as locale-neutral.
- Mobile summary/list responses remain bounded if added.

## Architecture Decision Bias

Prefer:

- Small shared locale helper.
- Durable profile-level preference.
- Explicit metadata.
- Stable canonical API values.
- Documentation for frontend clients.

Avoid:

- Hidden automatic translation.
- Route-specific locale forks.
- User-agent/device sniffing.
- Locale changes that mutate backend permissions, identity, or canonical status.
- Claims of visual mobile readiness without frontend/browser verification.
