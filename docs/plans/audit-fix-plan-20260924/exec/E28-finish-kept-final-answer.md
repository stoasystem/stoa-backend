# E28 最后一次尝试存下的答案要补完，不标 terminal

Status: released
Blocked by: 
Decision: [票据 16](../issues/16-attempt-three-kept-answer.md)
GitHub: #18

## Delivers

第三次尝试把答案存到命令上之后死掉，学生仍能收到这份已付费的答案，模型不再调用。

## Change

`attachment_repo.claim_message_ai_lease`：`ai_running`、lease 过期、`attempt=MESSAGE_AI_MAX_ATTEMPTS` 且 `provider_result_attempt` 等于它、答案 JSON 仍在 → 可领取，attempt 不增加；条件写同样加这一支。领取后由 `generate_for_command` 既有的「已存答案只补完」路径收尾。`jobs/conversation_generation.py`：带已存答案的过期 lease 不受年龄窗口限制，也不算 `stale_leases`、不被 E27 关闭。

## Acceptance

第三次尝试存答案后死 → 下一次 sweep：命令 `completed`、助手消息一条、模型调用次数不变、不发 `conversation_ai_attempts_exhausted`；第三次尝试未存答案的仍标 `terminal_failed`；带已存答案、超出 20 分钟的过期 lease 仍被补完。

## Poison

去掉领取里的补完分支 → 补完那条红；sweep 恢复按窗口过滤已存答案 → 超窗补完那条红。

## Commit

后端单独一个提交。

## Implementation (2026-09-25)

本地提交 1f2c9097，**未推送**。`attachment_repo.kept_answer_attempt`：存下的答案属于调用过模型的那次尝试才算（与 `conversations._stored_provider_result` 同口径）。领取：最后一次尝试带已存答案且 lease 过期 → 可领取、attempt 不增加，条件写同一支。`mark_message_command_terminal` 加 `attribute_not_exists(provider_result_json)`，请求路径也不会把带答案的命令标终态。sweep：已存答案不受 20 分钟窗口限制，但以提问时间起 **1 天**为限；超过即算 stale lease，由 E27 关闭并结算。
新用例 5 条（最后一次尝试补完、超窗补完、早先尝试的答案超窗补完、补完一天仍失败则放弃、终态写拒绝带答案命令）；全量 3913 passed。投毒 4 条均红：去掉补完领取、sweep 恢复按窗口、去掉一天上限、去掉终态写的条件。「未存答案的仍标 terminal_failed」由 E26 的用例覆盖。
偏离：票据决议写「允许再领取一次」，实现不限次数，改以「提问后一天」为界（核查指出补完若反复失败会无限重领且预留永不结算）；一天内每轮 sweep 重试补完，不调模型。

## Verification（地图会话，2026-09-25）

1f2c9097，未推送。与票据 16 对照：`kept_answer_attempt` 与 `conversations._stored_provider_result` 同口径（答案属于调用过模型的那次尝试才算）；最后一次尝试带已存答案且 lease 过期 → 可领取、attempt 不增加，条件写同一支；`mark_message_command_terminal` 加 `attribute_not_exists(provider_result_json)`；sweep 对已存答案不受 20 分钟窗口限制、不算 stale、不被 E27 关闭，但以提问后一天为界。新用例 5 条通过；全量 3913 passed；ruff 过。投毒 4 条各红（不可领取 → 2、恢复窗口过滤 → 2、去掉一天上限 → 1、终态写不拒绝 → 1）。

偏离（不限领取次数、改以一天为界）我认可：两轮审查指出补完反复失败会无限重领、预留永不结算，一天上限把它交回 E27 的结算；一天内每轮重试补完不调模型、无新成本。

## Released (2026-09-26)

1f2c9097，run 36193927645 success。
