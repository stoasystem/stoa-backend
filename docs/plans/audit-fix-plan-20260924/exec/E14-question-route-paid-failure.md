# E14 question 路由把带用量证据的 AI 失败落成 terminal 并补偿

Status: released
Blocked by: 
Decision: [票据 11](../issues/11-question-route-paid-failure.md)
GitHub: #21

## Delivers

在 question 路由上，截断或残缺 JSON 的答案不再被当成"结果未知"：provider 成本记账、预留补偿、效果 terminal，学生重放不会再调一次模型。

## Change

`src/stoa/routers/questions.py` 两处失败分支（约 1070 与 1573 行）：`isinstance(error, ai_service.AIInvocationFailure) and error.usage is not None` 时，先以 `error.usage` 观测 provider 用量，再走既有 `mark_question_effect_terminal(failure_code="provider_rejected")` 与 `_promote_terminal_effect` 的补偿路径；`usage is None` 的失败维持 `mark_question_effect_outcome_unknown`。若 `_observe_question_provider_usage` 只接受 `ai_response`，抽一个接受 `ProviderUsageEvidence` 的内部入口，两条路径共用。

## Acceptance

截断（`max_tokens`）与残缺 JSON（`end_turn`）各一条：效果 terminal、`failure_code=provider_rejected`、provider 成本证据一条、学生预留归零、随后重放同一命令不再调用模型；超时失败（无 `usage`）对照仍为 outcome_unknown；`tests/test_phase475_question_effect_recovery.py` 与 `tests/test_question_token_finalization.py` 全绿。

## Poison

把 `usage is not None` 的分支去掉 → 截断两条红（效果变回 unknown、成本证据缺失）。

## Commit

单独一个提交，只动后端；不依赖 E10–E13。

## Verification

2026-09-24 地图会话核查，提交 `389e8a3b`。与票据 11 逐条一致：带 `usage` 的失败先观测成本、再以 `technical_validation_passed=False` 归还预留、再走既有 terminal 路径 `provider_rejected`；无 `usage` 的失败仍 unknown。新测试 6 条通过（提交路径与丢失 intent 的恢复路径各两条、超时对照、完整答案对照），重放不再调用模型。投毒：去掉提交路径的 `usage` 分支 → 2 failed。

报告提出的边界（记账或归还失败时）已用探针核实（[evidence/test_e14_settle_failure_replay_probe.py](../evidence/test_e14_settle_failure_replay_probe.py)）：首次请求得到 503 `allowance_finalization_recoverable`，effect 停在 `invoking`、预留 `reserved`、成本证据 0 条；重放返回 201 `pending`，**没有第二次模型调用**。代价是那次调用的成本证据丢失，effect 要等既有 intent 过期的 exact-once 补偿才收敛。沿用既有模式，不算缺陷，记入地图。

全量后端套件（含两个 release-gate 文件，相邻 infra 目录现已存在）3764 passed / 1 failed，唯一失败是 `test_每个声明出来的lambda都会被后端部署更新`，是 E12 之后有意留红的部署列表检查（见 E18）。infra `tests/` 35 passed。所有提交**尚未推送**。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
