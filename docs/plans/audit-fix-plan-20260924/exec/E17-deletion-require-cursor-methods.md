# E17 删除扫描任务要求 repository 提供游标方法，并只保留一套扫描签名

Status: released
Blocked by: E07 已 verified
Decision: [票据 13](../issues/13-deletion-sweep-no-silent-fallback.md)
GitHub: #7

## Delivers

替身少两个方法不再换来旧行为：任务在任何 scan 或 claim 之前拒绝缺接口的 repository；扫描只有真实 repository 那一套签名。

## Change

`jobs/account_deletion.py`：入口检查 `get_deletion_scan_cursor`、`advance_deletion_scan_cursor`、`scan_pending_deletion_commands`、`claim_deletion_command` 四个可调用，缺一即抛 `AccountDeletionConflict`（或同类错误），不扫描；删除 `exclusive_start_key=` 加元组返回的分支与 `repository is account_deletion_repo` 的双路径，统一调用 `scan_pending_deletion_commands(limit=, cursor=)` 并读 `.items`/`.cursor`。迁移 `tests/test_phase473_account_deletion.py` 第 467 行附近的用例：改为真模块加 FakeTable，或给 `_AccountTable` 补齐两个游标方法与新签名。

## Acceptance

缺任一方法的 repository → 抛错，且 scan 与 claim 均未被调用（记录器为空）；真模块加 FakeTable 路径全部既有测试通过；phase473 那条迁移后通过；`.scratch/ai-audit-20260924/prior-issues` 的原审计见证在未适配时应改为**抛错**而非静默 `[0,0,0]`。

## Poison

恢复 `getattr` 探测与静默退回 → 「未被调用」那条红。

## Commit

单独一个提交，只动后端与测试。先于 R01 里的 #7 收尾。

## Verification

2026-09-24 地图会话核查，提交 `c0403c2e`。与票据 13 一致：四个方法缺一即抛 `AccountDeletionConflict` 并点名，不扫描不领取；只剩真实 repository 的 `scan_pending_deletion_commands(limit=, cursor=)` 一套签名与一条代码路径；phase473 那条用例迁到真模块加 FakeTable。新测试按缺失方法参数化 4 条，断言替身任何方法都未被调用。投毒：把探测恢复成不拒绝 → 4 failed。原审计见证在未适配时现在抛 `deletion repository lacks get_deletion_scan_cursor, advance_deletion_scan_cursor`，不再静默 `[0,0,0]`；我的适配见证已改到新签名并通过。

全量后端套件（含两个 release-gate 文件，相邻 infra 目录现已存在）3764 passed / 1 failed，唯一失败是 `test_每个声明出来的lambda都会被后端部署更新`，是 E12 之后有意留红的部署列表检查（见 E18）。infra `tests/` 35 passed。所有提交**尚未推送**。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
