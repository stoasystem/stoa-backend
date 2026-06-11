# Phase 142 UI Spec: Language Preference

## User-Facing Behavior

- The language switcher offers English and German only.
- Selecting German changes visible selected-flow copy to German without translating canonical API values.
- Authenticated users persist language preference through `PATCH /auth/me/preferences/locale`.
- On refresh, `/auth/me` locale fields restore the effective frontend language.
- Toast notifications avoid covering the compact top-right language control.

## States

- Pending preference update: language controls are disabled while the locale mutation is in flight.
- Demo fallback: language changes persist through local i18next storage and the demo `/auth/me` fallback reflects the stored supported locale.
- Unsupported stored locale: frontend falls back to English.

## Accessibility And Layout

- Existing language switcher ARIA labels remain in place.
- Compact dropdown items use short labels `EN` and `DE`.
- Footer/select variants keep localized display labels and canonical option values separate.

