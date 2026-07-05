# Phase 260 Verification

## Commands

```bash
.venv/bin/python -m pytest tests/test_external_activation_smoke.py tests/test_release_evidence.py tests/test_core_smoke.py -q
```

Result: `20 passed in 1.31s`

```bash
.venv/bin/python -m ruff check src/stoa/services/external_activation_service.py src/stoa/routers/admin.py tests/test_external_activation_smoke.py
```

Result: `All checks passed!`

## Evidence

- Development runtime returns `overallState=locally_ready` and `production_environment_not_selected`.
- Production runtime returns `overallState=read_only_verifiable`, not live-passed.
- All API and browser smoke entries are marked `mutation=false`.
- The report includes the release evidence validator route and no-mutation fixture/mode policy.
- Endpoint is admin-only.
