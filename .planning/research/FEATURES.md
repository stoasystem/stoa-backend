# v4.1 Feature Research: Mobile And Multilingual Polish Foundation

**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Researched:** 2026-06-11

## Feature Direction

v4.1 should create a durable foundation for mobile and multilingual polish without pretending this backend repository can complete all frontend visual work alone. The strongest scope is:

1. Mobile-ready API contracts and gap audit.
2. Locale preference storage and retrieval.
3. Language metadata and fallback behavior for client-facing responses.
4. Verification that canonical backend data remains stable across locales.
5. Release documentation that separates completed backend work from deferred frontend/native UI implementation.

## Must Have

### Mobile Contract Readiness

- Identify mobile-critical role flows:
  - Student practice, questions, assignments, progress.
  - Parent child overview, reports, progress, tutor status.
  - Tutor queue/detail/status workflows.
  - Admin operational views where mobile access is plausible.
- Audit route payloads for mobile pain points:
  - Large nested payloads without pagination or summaries.
  - Missing compact list/detail separation.
  - Error states that are hard for clients to render clearly.
  - Inconsistent timestamps or status codes.
- Define backend contract expectations for mobile clients:
  - Stable IDs and status codes.
  - Compact list responses where needed.
  - Explicit loading/error/retry-friendly response semantics.
  - No backend browser sniffing.

### Multilingual Foundation

- Add authenticated user/profile locale preference support.
- Normalize accepted locale values and provide deterministic fallback.
- Support at least English and German foundation contracts (`en`, `de`) because existing subject/language context already references English and German.
- Return locale/language metadata where content language matters.
- Preserve canonical identifiers, enum values, status values, and database keys across locales.
- Define which fields are translatable display text and which fields are canonical data.

### Cross-Role API Polish

- Expose locale preferences consistently to roles that need them.
- Avoid duplicating locale logic in every router.
- Keep authorization behavior unchanged while adding locale fields.
- Ensure existing clients that do not send locale data continue to work.
- Add tests for missing, supported, unsupported, and changed locale values.

### Planning And Release Evidence

- Update the feature gap audit so v4.1 does not leave stale v4.0 language.
- Record which mobile and multilingual work is implemented in backend versus deferred to frontend/native.
- Capture UAT criteria for mobile readiness as API and documentation verification in this repo.

## Should Have

- Optional `Accept-Language` based defaulting when no stored preference exists.
- Role-aware compact response variants for the heaviest mobile list routes.
- Localized display label map for small, stable status vocabularies if the product needs it during v4.1.
- Contract tests proving display labels can change without mutating canonical values.
- Documentation for frontend clients on locale preference, fallback, and formatting responsibilities.

## Defer

- Full frontend responsive redesign unless the frontend workspace is made available.
- Native mobile application work.
- Machine translation or translation memory.
- Admin translation management UI.
- RTL visual layout verification.
- Localized AI prompt generation or tutoring content rewriting.
- Legal/compliance localization.

## Recommended Feature Grouping

1. **Contract and audit phase:** define mobile/i18n boundaries, update feature gap audit, and create UAT criteria.
2. **Locale preference phase:** implement durable locale storage, normalization, APIs, and tests.
3. **Route polish phase:** apply metadata/fallback patterns to role-critical responses and add mobile-friendly contract checks.
4. **Release gate phase:** verify documentation, regression behavior, and remaining frontend/native gaps.

## Source Notes

- MDN Responsive Design: responsive design uses flexible layouts, fluid media, and breakpoints rather than separate device-specific backends.
- MDN Intl: client platforms can format locale-sensitive values with built-in internationalization APIs when APIs provide stable data.
- W3C language and directionality guidance: language and text direction should be explicit metadata where content depends on it.
- WCAG 2.2: mobile polish should consider reflow, target size, focus visibility, and non-pointer alternatives, though frontend verification belongs in the UI workspace.
