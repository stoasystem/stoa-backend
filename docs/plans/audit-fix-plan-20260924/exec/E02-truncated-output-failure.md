# E2 截断的结构化输出落成可恢复失败

Status: released
Blocked by: 
Decision: [票据 02](../issues/02-truncated-output-terminal-state.md)
GitHub: #21

## Delivers

`max_tokens` 截断或残缺 JSON 不再以成功答案持久化；学生得到既有的可重试失败，预留额度释放，用量证据保留。

## Change

`ai_service.py`：在两条路径解析之前判 `stop_reason == "max_tokens"` → `AIInvocationFailure("incomplete_output")`，但先完成 `parse_provider_usage` 并把用量证据带在失败上（或先落证据再抛）；`_parse_ai_response` 对去空白、去围栏后以 `{` 开头却解析失败的文本抛 `malformed_response`，`_validate_output` 第 3 步不得再把它回退成原文。路由 `conversations.py` 2362 行恢复路径核实能观测用量并 `_restore_message_allowance`。

## Acceptance

stream 与 buffered 各一条 `max_tokens` 加残缺 JSON → `incomplete_output`、command 不落 `sent`、预留释放、用量证据存在；`max_tokens` 加完整 JSON → 只触发第一道检查；`end_turn` 加残缺 JSON → 只触发第二道；完整答案两条对照通过。

## Poison

去掉 `max_tokens` 判定 → stream/buffered 两条红；恢复原文回退 → `end_turn` 加残缺 JSON 那条红。

## Commit

单独一个提交。`bedrock_max_tokens` 默认值 2048 不动。

## Verification

2026-09-24 地图会话核查，提交 `972cefe2`。`tests/test_truncated_ai_output.py` 18 条通过，截断用例按 stream/buffered 参数化，含 `max_tokens` 加完整 JSON、`end_turn` 加残缺 JSON 两条分离检查，以及命令级「不落 sent、预留释放、用量证据保留」见证。投毒：去掉 `max_tokens` 判定 → 4 failed；恢复原文回退 → 6 failed。`bedrock_max_tokens` 未动。

  **留意**：提交信息自述 question 路由的 buffered 路径上，截断现在走 provider 超时那条失败路径，effect 标为结果未知、预留**不释放**；释放不在本次范围。已记入地图 Not yet specified。

全量离线回归（排除依赖相邻 infra 根目录的两个 release-gate 文件）3541 passed / 0 failed；`test_formal_release_gate.py` 的一条失败在这五个提交之前的 a015a444 上同样失败，属既有 infra 根目录问题。ruff 对改动文件全部通过；mypy 报错都在未改动的文件里。与远端 origin/main 新增的 4 个提交（b7b1b4f8…ef0827c9）在临时 worktree 里合并无冲突，重叠文件相关 308 条测试通过。五个提交**尚未推送**，未部署。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
