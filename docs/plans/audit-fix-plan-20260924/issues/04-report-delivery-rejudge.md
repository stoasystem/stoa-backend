# 周报生成路径的投递前应如何重判当前关系（#3 余量）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#3](https://github.com/stoasystem/stoa-backend/issues/3)

## Question

c1eee5f 之后，重发路径已在发信前调用 `parent_link_service.current_relationship`；生成路径 `report_service.store_and_send_weekly_report` 投递前仍只有 `require_active_account_fence(student_id)`。卡 022 B-1 实测：payload 判完后撤销关系，被撤销家长仍收到孩子周报正文，窗口为 AI 生成加 S3 写入。

要决定：
1. 重判放在哪：SES 发送前一刻在 `store_and_send_weekly_report` 内判，还是下沉到 `notify_service.send_fenced_weekly_report_email` 让所有周报出口共享。
2. 判定失败后报告记录怎么落：新增 `withheld` 类状态、保留 artifact 但不发；还是复用 `email_failed`。artifact 里已有孩子私密内容，是否要删。
3. 收件地址来源：继续用 payload 里的 `parent_email`，还是投递时从当前关系解析家长当前地址（重发已这么做）。
4. 术语对齐：CONTEXT.md 只有"家长绑定"，代码的唯一判据是"当前关系"且覆盖旧绑定与新 link。本票据顺带把这两个词在 CONTEXT.md 里写清，不写实现细节。
5. 覆盖：artifact 生成后撤销、旧绑定撤销、新 link 有效、账号删除中；卡 022 C-1 提到的两份等价判据实现是否顺手合并，写明取舍。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

把重发路径的「当前关系 → 家长当前邮箱」抽成一个共享解析函数，但返回值让调用方区分三种结果：关系不存在、关系成立但邮箱缺失、成立且有邮箱。生成路径在 `store_and_send_weekly_report` 内、耗时准备（AI 生成、S3 写入）完成后、调 SES 前一刻重判；重发路径同样在实际发送前重判。关系不存在 → 不发信，状态复用 `email_failed`，`email_error_class = relationship_revoked`；邮箱缺失 → 不发信，`email_error_class = recipient_missing`；不新增状态。收件地址一律取自家长当前 profile，不再用 payload 存的。artifact 保留，重发路径的重判继续拒绝。
术语：CONTEXT.md 补「当前关系」，说明「家长绑定」是它的一种成立形式（已在本次写入）。卡 022 C-1 的两份等价实现不在本票据合并。
验收：payload 判后撤销 → 无 SES 调用、`email_failed/relationship_revoked`；payload 生成后邮箱变更 → 发到当前邮箱；当前邮箱缺失 → 不发送、`recipient_missing`；有效新 link → 正常发出；投毒去掉重判必红。实施票据 [E4](../exec/E04-report-delivery-rejudge.md)。
