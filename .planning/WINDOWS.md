---
schema_version: 1
open_count: 1
waived_count: 0
fixed_count: 0
total_count: 1
last_updated: 2026-07-30T16:16:48.635Z
---

# Broken Windows Ledger

> Cross-phase defect register. `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 474 | unrun-verify | stoa-infra/stacks/lambda_dist_guard.py |  | Full CDK synth remains NOT RUN until the backend provides a valid dist manifest; stale override was not used. | open |  | 2026-07-30T16:16:48.635Z |  |

````json
[
  {
    "id": 1,
    "kind": "unrun-verify",
    "phase": "474",
    "file": "stoa-infra/stacks/lambda_dist_guard.py",
    "line": null,
    "description": "Full CDK synth remains NOT RUN until the backend provides a valid dist manifest; stale override was not used.",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-07-30T16:16:48.635Z",
    "resolved_at": null
  }
]
````
