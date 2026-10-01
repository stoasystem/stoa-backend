# 缺游标方法的注入 repository 应拒绝还是静默退回（E7 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by:
GitHub: [#7](https://github.com/stoasystem/stoa-backend/issues/7)

## Question

`run_pending_deletions` 用 `getattr` 探测 repository 是否提供 `get_deletion_scan_cursor` 与 `advance_deletion_scan_cursor`，缺失时静默退回不持久化游标的旧行为。这是卡 022 C-9 点名的替身逃生口那一类，也是原审计见证仍红的原因。任务该拒绝这样的 repository，还是继续容忍？

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

**缺接口立即失败。** 任何 scan 或 claim 之前先要求两个游标方法存在，缺失即抛错，不做任何扫描；同时只保留真实 repository 的扫描签名（`scan_pending_deletion_commands(limit=, cursor=)` 返回带 `.items`/`.cursor` 的页），删掉对 `exclusive_start_key=` 加元组返回的第二套协议。

事实修正：仓库自己的测试并非全部已满足。`tests/test_phase473_account_deletion.py::test_scheduled_discovery_recovers_lost_route_trigger_and_reconstructs_service` 注入的 `_AccountTable` 只有 scan 与 claim，需要迁移到真模块加 FakeTable 或给替身补齐两个方法。补一条「缺接口时 scan 与 claim 均未被调用」的测试。

实施票据 [E17](../exec/E17-deletion-require-cursor-methods.md)。

## Comments

2026-09-25：E17 关掉了 job 层的探测，但 `account_deletion_repo.scan_pending_deletion_commands`（:1536）与 `claim_deletion_command`（:1690）仍各留一个**表级**钩子 `getattr(target, "<name>", None)`：一个带同名方法的表替身仍能绕开真实 Scan 的 Limit-before-filter 语义。E17 之后 `tests/test_phase473_account_deletion.py::_AccountTable` 上的这两个方法已无调用方。决议的精神（不留逃生口）延伸到这两处 → E23。其余 18 个表级钩子（含卡 022 C-9 的 `delete_owned_row`）归 stoa-docs 卡 070/075。
