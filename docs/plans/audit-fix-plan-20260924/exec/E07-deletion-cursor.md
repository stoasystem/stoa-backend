# E7 定时删除扫描跨调用持久化游标

Status: released
Blocked by: 
Decision: [票据 09](../issues/09-deletion-sweep-progress.md)
GitHub: #7

## Delivers

超出单次扫描预算的删除命令在后续调度轮中被发现；整表按周期轮转，不再每次从头扫。

## Change

`account_deletion_repo`：新增读/写 `PK=JOB#account_deletion / SK=SCAN_CURSOR`（`cursor`、`version`、`cycle_started_at`），写入条件 `version = :expected`；`jobs/account_deletion.py::run_pending_deletions`：起点取存的游标，本批命令逐项 claim 尝试之后再推进游标，扫到表尾归零并递增 version。远端调度事实：`rate(5 minutes)`、`limit=25`。

## Acceptance

2,600 条无关行后的命令第二轮被发现；零匹配页继续；扫完归零后下一轮从头；归零后迟到的旧 version 写入被拒；扫描后中断、重启从存的游标继续；并发两轮条件写只有一个成功；`test_phase473_account_deletion.py` 全绿。

## Poison

去掉游标读取 → 第一条红；去掉 version 条件 → 迟到写入那条红。

## Commit

单独一个提交。决议里记周期估算：每轮 ≤2,500 行评估量，5 分钟一轮。

## Verification

2026-09-24 地图会话核查，提交 `a72c7be3`（主体）与 `05727d3a`（复核后补丁，同一票据两个提交，偏离「一张卡一个提交」但边界清楚）。

**对照决议 09**：控制行 `JOB#account_deletion / SCAN_CURSOR`，字段 `cursor`、`version`、`cycle_started_at`；条件写绑定 version，表尾归零同样递增；本批命令逐项 claim 尝试之后才写游标；无 GSI、无队列；调度事实写入提交信息（5 分钟一轮、limit 25、每轮 ≤2,500 行）。全部一致。

**测试**：`tests/test_account_deletion_sweep_cursor.py` 14 条通过，覆盖 2,600 行后第二轮发现、零匹配页、归零后新周期、迟到写入被拒、扫描后中断、命令处理中被硬停、并发两轮只存一处、畸形游标读作表头、version 0 行仍前进、畸形 `cycle_started_at` 丢弃。相关既有套件（phase473 删除、fakes 门禁与保真、decommission、dist build）合计 107 passed；全量离线回归 3555 passed / 0 failed。ruff 通过；mypy 报错均在未改文件。

**投毒**：去掉游标读取 → 9 failed；去掉 version 条件 → 2 failed（迟到写入、并发）；把写游标挪到 claim 循环之前 → 2 failed（中断、失败保持）。

**原审计见证**：`.scratch/ai-audit-20260924/prior-issues/test_prior_regressions.py::test_deletion_sweeps_eventually_reach_commands_beyond_scan_budget` **仍红**（起点 `[0,0,0]`）：审计替身没有 `get_deletion_scan_cursor`/`advance_deletion_scan_cursor`，任务在替身缺这两个方法时静默退回旧行为。给替身补上内存版控制行后（[evidence/test_issue7_audit_witness_adapted.py](../evidence/test_issue7_audit_witness_adapted.py)）通过：三轮起点 `[0, 2500, 0]`，late-command 第二轮被发现。关 #7 时应引用这个适配见证并说明原因。

**留意（待拍板，见地图）**：
1. 05727d3a 让「claim 或 continue 失败」保持游标不前进。一条持续失败的命令会让整表扫描停在它那一片，后面的命令无限期不被发现，正是 #7 那类饥饿的另一种形态；提交信息自认「持续失败怎么办未决定」。
2. 任务对注入的 repository 缺游标方法时静默退回不持久化，是卡 022 C-9 点名的替身逃生口那一类；生产路径用真模块不受影响，但审计见证因此仍红。

2026-09-24 复核补充：适配见证只证明 job 的控制流，未执行真实 repository 的条件写，也未模拟跨进程持久化，且文件在未跟踪的 `.scratch/` 里。关 #7 以已提交的 `tests/test_account_deletion_sweep_cursor.py`（真实 repository 加 FakeTable）为主要依据，适配见证只作补充。两处待拍板已落成票据 12、13 与 E16、E17。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
