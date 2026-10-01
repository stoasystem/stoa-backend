# E3 Accept-Language 按权重协商

Status: released
Blocked by: 
Decision: [票据 03](../issues/03-accept-language-q-values.md)
GitHub: #20

## Delivers

`de;q=0, en;q=1` 选出英语；被明确排除的语言不再写进 OUTPUT LANGUAGE。

## Change

`src/stoa/services/locale_service.py::locale_from_accept_language` 按票据 03 决议重写：解析 q、跳过畸形项、剔除 q≤0、稳定降序、取第一个受支持基语言，否则 None。

## Acceptance

`de;q=0,en;q=1 → en`；`fr;q=0.2,en;q=1 → en`；全 q=0 → None；`en;q=0.8,fr;q=0.8 → en`（同权保序）；`de-CH → de`；`en;q=abc,fr → fr`（畸形跳过）；单语言四种与缺头 profile 回退对照保持。

## Poison

把排序去掉 → 前两条红。

## Commit

单独一个提交。

## Verification

2026-09-24 地图会话核查，提交 `71a7adf4`。15 条正例、7 条无可用语言、单语言与 profile 回退对照全部通过，含同权保序、`de-CH → de`、畸形 q 跳过。投毒：去掉排序 → 3 failed。

全量离线回归（排除依赖相邻 infra 根目录的两个 release-gate 文件）3541 passed / 0 failed；`test_formal_release_gate.py` 的一条失败在这五个提交之前的 a015a444 上同样失败，属既有 infra 根目录问题。ruff 对改动文件全部通过；mypy 报错都在未改动的文件里。与远端 origin/main 新增的 4 个提交（b7b1b4f8…ef0827c9）在临时 worktree 里合并无冲突，重叠文件相关 308 条测试通过。五个提交**尚未推送**，未部署。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
