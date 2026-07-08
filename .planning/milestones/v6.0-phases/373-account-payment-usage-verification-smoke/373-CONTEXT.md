# Phase 373 Context

## Phase Boundary

Phase 373 verifies account, payment, usage, entitlement, quota, verification, and support explanation surfaces using approved accounts or explicit blocked states.

## Decisions

- Account smoke remains read-only or disabled unless production mutation is explicitly approved for a pilot-safe account.
- Every surface requires request IDs and account aliases rather than private user data.
- Login-code/passwordless behavior is checked as a policy state and must not imply token minting unless a real approved flow exists.
- Missing evidence blocks the phase instead of being treated as a local contract pass.

## Existing Code Insights

- v5 account and revenue gates already model entitlement, billing, and usage reliability.
- The v6 layer composes those ideas into a current evidence smoke without introducing provider writes.
