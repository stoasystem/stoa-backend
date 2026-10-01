# 第三次尝试已存下的答案在标 terminal 时被丢弃，应如何处置（票据 15 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: #18

## Question

2026-09-25 已在 worker 测试替身上复现：`generate_for_command` 领取失败且 `attempt>=3` 时，直接 `mark_message_command_terminal`，不看命令上的 `provider_result_json`。第一、二次尝试死后，下一次领取会按票据 08 约束 2 先把已存答案补完，不再调模型；第三次尝试死后没有「下一次领取」，所以它已付费、已存下的答案被丢掉，学生看到 `attempts_exhausted`。E27 之后，这类命令的 effect 停在 `observed`，只做 restore，账本是对的；丢的是答案本身。

E27 上线后，这类命令在 `terminal_at` 满 10 分钟会被结算，effect 从 `observed` 变为 `restored`。若本票据决定补完答案，补完路径要么在 E27 结算之前完成，要么能在 effect 已 restored 时只写答案、不再动账本。

要定：
1. 是否算缺陷：已存答案是否应在标 terminal 之前按「已存答案只补完」收尾（不调模型）？
2. 若是，收尾放在哪：`generate_for_command` 标 terminal 之前，还是 sweep 另开一类候选？
3. 先复现再定，还是按读码直接修？

复现结果：第一次尝试存下答案后死，把命令改成 attempt=3、调用与答案标记都指向 3、lease 过期 → sweep 一轮后命令 `terminal_failed`，助手消息 0 条，模型未再调用，`provider_result_json` 仍留在命令上。

## Answer

2026-09-25 用户决议：**算缺陷，只修今后，不回填**。
1. 最后一次尝试死前已存答案的，允许再领取一次，只为补完存下的答案（不调模型、不增加 attempt），之后照常结算；不再标 `terminal_failed`。
2. 补完不调模型、不产生新成本，所以 sweep 对带已存答案的过期 lease 不受 20 分钟年龄窗口限制；E27 的超窗关闭相应跳过这类命令，免得先关闭再丢答案。
3. 已经 `terminal_failed` 的历史命令不回填：E27 已 restore 其预留，学生早已离开。
实施票据 [E28](../exec/E28-finish-kept-final-answer.md)。
