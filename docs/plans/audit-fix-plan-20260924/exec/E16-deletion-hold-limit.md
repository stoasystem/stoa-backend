# E16 失败命令最多按住游标三轮，并修正周期完成时间

Status: released
Blocked by: E07 已 verified
Decision: [票据 12](../issues/12-deletion-sweep-hold-limit.md)
GitHub: #7

## Delivers

一条持续失败的删除命令最多让扫描在原地重试三轮，第四轮越过它并记名；被越过的命令状态、lease、检查点原样保留。周期完成日志的时间与时长真实。

## Change

`account_deletion_repo`：`DeletionScanCursor` 加 `held_runs: int`；`advance_deletion_scan_cursor` 接受 `held_runs`，与 cursor/version 同一条件写。`jobs/account_deletion.py`：失败保持时以 `held_runs+1`、同 cursor、`version+1` 条件写（落败不计）；`held_runs >= 3` 且本轮再失败 → 推进游标、`held_runs=0`、警告 `account_deletion_scan_skipped command_ids=...`；推进或归零一律清零；扫描异常、无效分页、硬中断不写游标不计数；开头被按住时保留首次 `cycle_started_at`。完成日志：归零条件写成功后 `completed = datetime.now(UTC)`，`completed_at` 与 `duration_seconds` 用它。

## Acceptance

同一命令连续失败：前三轮游标与 held_runs 为 1/2/3、version 各加一；第四轮推进、held_runs 归零、警告含 command_id；被越过命令的行、lease、检查点与失败前逐字相同。并发两轮同一 version 上失败只计一次。失败后成功一轮 → held_runs 归零。扫描异常轮不计数。合成时钟下耗时 10 秒的归零轮，日志 `duration_seconds=10` 且 `completed_at` 晚于入口时间。既有 14 条游标测试与 phase473 套件全绿。

## Poison

去掉上限判断 → 第四轮推进那条红；把 `completed` 改回入口 `now` → 时长那条红；让越过时改写命令状态 → 状态保持那条红。

## Commit

单独一个提交，只动后端。先于 R01 里的 #7 收尾。

## Verification

2026-09-24 地图会话核查，提交 `aaf27cba`。与票据 12 逐条一致：`held_runs` 与 cursor、version 同一条条件写；按住那轮 version 递增，同 version 并发失败只计一次；第 3 次记录后下一轮仍先尝试、再失败才推进并记 `account_deletion_scan_skipped` 含 command_id；被越过命令的行逐字节不变；扫描异常不写不计；周期开头被按住保留首次 `cycle_started_at`；完成时间改为归零条件写成功后取。新测试 7 条通过，含合成时钟 10 秒周期日志 `duration_seconds=10`。投毒：去掉上限 → 1 failed（第四轮仍按住）。

全量后端套件（含两个 release-gate 文件，相邻 infra 目录现已存在）3764 passed / 1 failed，唯一失败是 `test_每个声明出来的lambda都会被后端部署更新`，是 E12 之后有意留红的部署列表检查（见 E18）。infra `tests/` 35 passed。所有提交**尚未推送**。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
