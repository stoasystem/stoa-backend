# E23 摘掉删除扫描的两个表级钩子

Status: released
Blocked by:
Decision: [票据 13](../issues/13-deletion-sweep-no-silent-fallback.md)
GitHub: #7

## Delivers

一个带同名方法的表替身不再能替换 sweep 的发现与领取语义；扫描与条件领取只有真实实现一条路。其余表级钩子留给 stoa-docs 卡 070/075。

## Change

`src/stoa/db/repositories/account_deletion_repo.py`：删除 `scan_pending_deletion_commands` 里的 `hook = getattr(target, "scan_pending_deletion_commands", None)` 分支与 `claim_deletion_command` 里的同类分支，直接走 `_scan` / 条件 `update_item`；`tests/test_phase473_account_deletion.py::_AccountTable` 删掉已无调用方的同名两个方法（若 grep 证实仍有调用方则先迁到 FakeTable）。可选：`renew_deletion_command_claim`（:1767）同法处理，若其测试也已全走 FakeTable。

## Acceptance

`grep -n 'getattr(target, "scan_pending_deletion_commands"\|getattr(target, "claim_deletion_command"' src/stoa/db/repositories/account_deletion_repo.py` 为空；`tests/test_account_deletion_sweep_cursor.py`、`tests/test_phase473_account_deletion.py` 全绿；一个只实现同名方法而不实现 `scan`/`update_item` 的表替身传给真实 repository 时抛错而不是被采用。

## Poison

把 scan 的钩子分支加回 → 「替身不被采用」那条红。

## Commit

单独一个提交，只动后端；不依赖其他票据。若 stoa-docs 卡 070 先落地并覆盖这两处，本票据关闭。

## Implementation (2026-09-25)

本地提交 8433b39e，**未推送**（排在未推送的 E21 7c8d46e0 之后，但不依赖它）。摘掉扫描、领取与续约三个表级钩子（续约按「可选」一并处理：没有任何表替身定义它，claim_fencing 里的是 repository 替身）；_AccountTable 的两个同名方法无调用方，已删。三条「只按名字应答的表替身被拒绝」测试；把 scan 钩子加回 → 发现那条红。全量 3889 passed。

## Verification（地图会话，2026-09-25）

提交 8433b39e，未推送。摘掉 `scan_pending_deletion_commands`、`claim_deletion_command`、`renew_deletion_command_claim` 三个表级钩子，只走真实 `scan` 与条件 `update_item`；`_AccountTable` 上无调用方的两个同名方法删除。新测试 3 条（只按名字应答的表对三步各被拒绝且未被调用）通过；全量 3889 passed。投毒：把 scan 钩子加回 → 1 failed。其余 17 个表级钩子归 stoa-docs 卡 070/075。

## Released (2026-09-25)

随 8433b39e 推送，run 36181425450 success。
