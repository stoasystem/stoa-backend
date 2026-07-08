# Phase 376 Context

## Phase Boundary

Phase 376 closes v6.0 by running the current real pilot start gate and producing either a narrow cohort start package or an executable blocker package.

## Decisions

- `start_limited_pilot` requires ready inventory, account smoke, provider evidence, and launch packet evidence.
- `hold` is the default when evidence is incomplete and no blockers have been explicitly accepted.
- `harden_further` is used when blockers are accepted but unresolved evidence still requires a hardening path.
- v6.1 real cohort operations are allowed only when the gate returns `start_limited_pilot`.

## Existing Code Insights

- v5.35 `real_pilot_start_decision_gate` remains available for the prior local contract chain.
- v6.0 uses a distinct `v6_pilot_start_or_blocker_decision_gate` to avoid confusing local v5 contracts with current real evidence.
