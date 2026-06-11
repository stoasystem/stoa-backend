# v4.1 Pitfalls Research: Mobile And Multilingual Polish Foundation

**Milestone:** v4.1 Mobile And Multilingual Polish Foundation
**Researched:** 2026-06-11

## Main Pitfalls

1. **Claiming frontend completion from a backend-only repo**
   - The repository can provide mobile-ready contracts and gap documentation. It cannot prove responsive screens, touch targets, keyboard behavior, or visual localization without the frontend workspace and browser/device verification.

2. **Server-side browser or device sniffing**
   - Responsive support should come from client layout and stable API contracts. Backend user-agent branches are brittle and can create inconsistent behavior.

3. **Locale only in JWT/session state**
   - Locale preference should be stored durably on profile/user records. Token-only locale disappears across sessions and is hard to update consistently.

4. **Translated values becoming canonical state**
   - Statuses, IDs, enum values, subject codes, and route behavior must remain stable. Localized display labels, if added, should be separate fields.

5. **Implicit or lossy fallback behavior**
   - Unsupported, missing, malformed, and partially supported locales need deterministic behavior. Tests should cover each path.

6. **Over-localizing user or AI content**
   - Tutor notes, student free text, generated explanations, and report content may have meaning, consent, privacy, or quality implications. v4.1 should tag language and support display, not automatically rewrite content.

7. **Ignoring directionality and future language expansion**
   - English/German are left-to-right, but contracts should not make later `dir` or per-field language metadata impossible.

8. **Confusing locale, language, and timezone**
   - Locale formatting is not the same as content language or user timezone. Dates/times should remain canonical in API data, with formatting left to clients unless a specific backend display field is required.

9. **Mobile payload bloat**
   - Large nested responses create bandwidth, latency, and render problems on mobile. Use compact summaries, pagination, and detail endpoints where needed.

10. **Accessibility treated as cosmetic**
    - Mobile polish should account for reflow, focus visibility, target size, dragging alternatives, and language metadata. In this repo, those become frontend UAT criteria and API support notes.

11. **Route-specific locale logic drift**
    - Locale normalization and fallback should live in shared helper/service code. Reimplementing it per router will produce inconsistent behavior.

12. **Breaking existing clients**
    - Locale fields must be additive or explicitly versioned. Existing clients without locale inputs should continue to receive valid responses.

13. **Privacy leakage through mobile summaries**
    - Compact responses should not accidentally expose private report artifacts, tutor notes, or sibling data while trying to simplify mobile UI work.

14. **Stale planning artifacts**
    - Existing research and gap-audit files still contain older milestone language. v4.1 should update those artifacts so autonomous phase planning does not inherit obsolete v4.0/v1.6 assumptions.

## Mitigations

- Define backend/mobile/frontend boundaries before implementation.
- Add locale preference as durable profile data with shared normalization.
- Keep canonical API state locale-neutral.
- Use explicit `locale`/`language` metadata where content needs it.
- Write regression tests for unchanged authorization and canonical values.
- Treat mobile UI completion as deferred unless the frontend workspace is available and visually verified.
- Update feature gap documentation during the milestone release gate.

## Planning Questions To Resolve

- Should unsupported locale inputs be rejected with a validation error, coerced to default, or stored only if on an allowlist?
- Is the initial supported set exactly `en` and `de`, or does product need a broader allowlist now?
- Which role owns changing a child's locale preference: student, parent, admin, or multiple roles?
- Which existing routes are actually heavy enough to require compact mobile response variants in v4.1?
- Should `Accept-Language` be advisory only, or part of the formal API contract?
