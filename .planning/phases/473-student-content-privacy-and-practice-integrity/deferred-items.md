# Deferred Items

- **Plan 473-24 full-suite verification (2026-07-17):** `tests/test_phase473_practice_authorization.py` has two pre-existing clock-dependent failures after its fixed `NOW + 1 hour` assignment crossed real wall time. The focused file reports 39 passed and 2 failed; the full suite reports 1676 passed and the same 2 failures. This is outside Plan 473-24's document-boundary scope and should be repaired by injecting the test clock at the route authorization boundary rather than extending a hard-coded timestamp.
