# 支付解冻前，权益子女判据应如何改到当前关系（卡 022 B-2）

Labels: wayfinder:grilling
Type: grilling
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#22](https://github.com/stoasystem/stoa-backend/issues/22)

## Question

`entitlement_service._active_child_ids` 只读正向绑定行的 status；反向撤销时 `current_relationship` 已判 None，它仍返回该孩子。今天 `GET /parents/me/subscription` 被 `refuse_if_frozen()` 与 `BILLING_AND_SUBSCRIPTION_ENABLED = False` 挡住，所以未泄露；开关翻 True 当天就会把 `studentId` 与套餐状态交给已撤销的家长。

要决定：
1. 改法：让它走 `parent_link_service.current_children`，还是删掉私有实现只保留一条判据。
2. 闸：是否加一条测试，断言"支付开关为 True 时，权益子女集合等于当前关系集合"，保证有人翻开关前这条先红。
3. 卡 022 C-4（`paid_entitlement_service.relationship_authority` 仍仅凭 profile 的 `parent_id`）是否同源、是否并入。
4. 决议要给票据 06 一段可直接发布的 GitHub issue 正文（英文，含固定提交链接、复现、验收）。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

`_active_child_ids` 正文换成对 `parent_link_service.current_children(parent_id)` 的映射，删掉自己那份「正向绑定 status 加 active_children」的并集。闸：负例必须针对**旧绑定**：旧 binding 正向 `active`、反向 `revoked`、且没有其他有效新 link 时，权益列表不含该孩子；只测新 link 的反向撤销证明不了 B-2。
C-4 另立卡，不并入；准确表述：`paid_entitlement_service._profile_claims_binding` 判 `parent_id` 加 `parent_binding_status == active`，不读反向行；事务内 ConditionCheck 只保护写入路径，不能证明所有只读调用受保护。实施票据 [E5](../exec/E05-entitlement-current-children.md)；GitHub issue 发布见票据 06，正文英文稿如下。

```
[P1] Entitlement child resolution trusts the forward binding row and survives a reverse revocation

`entitlement_service._active_child_ids` unions legacy `parent_student_binding` rows whose forward `status` is active with `parent_link_service.active_children`. When a relationship is revoked on the reverse row only, `parent_link_service.current_relationship` already answers None, but the entitlement child set still contains that student. The parent-facing `GET /parents/me/subscription` route is currently blocked by the billing freeze (`refuse_if_frozen()`, `BILLING_AND_SUBSCRIPTION_ENABLED = False`); administrator billing views also consume the entitlement list. If billing is unfrozen before this predicate changes, a revoked parent could receive the child's `studentId` and plan state through that route.

**Audited revision:** `5a6ba852cd8f778701c2f99ffe9e54c0c9bbbcbd` (business code unchanged at current HEAD). **Priority:** P1 (must land before billing unfreeze). **Origin:** stoa-docs card 022, finding B-2.

### Source

- [src/stoa/services/entitlement_service.py:156-169](https://github.com/stoasystem/stoa-backend/blob/5a6ba852cd8f778701c2f99ffe9e54c0c9bbbcbd/src/stoa/services/entitlement_service.py#L156-L169) `_active_child_ids`
- [src/stoa/services/parent_link_service.py:515-525](https://github.com/stoasystem/stoa-backend/blob/5a6ba852cd8f778701c2f99ffe9e54c0c9bbbcbd/src/stoa/services/parent_link_service.py#L515-L525) `current_relationship`
- [src/stoa/services/parent_link_service.py:541-553](https://github.com/stoasystem/stoa-backend/blob/5a6ba852cd8f778701c2f99ffe9e54c0c9bbbcbd/src/stoa/services/parent_link_service.py#L541-L553) `current_children`

### Verification so far and suggested offline reproduction

Confirmed by source inspection only: `_active_child_ids` reads the forward binding `status` and `active_children`, neither of which consults the reverse row that `current_relationship` judges. No HTTP response has been captured and no dedicated Moto run exists yet for this finding.

Suggested reproduction (Moto, synthetic identities, no AWS): store a legacy binding with forward `status="active"` and a reverse row `status="revoked"`, with no other link; assert `current_relationship(parent, student)` is None while `_active_child_ids(parent)` still contains the student.

### Expected behavior / acceptance

Resolve entitlement children through the single current-relationship predicate (`current_children`). Add a regression asserting the reverse-revoked legacy binding is excluded, with a valid current link as positive control. Land before `BILLING_AND_SUBSCRIPTION_ENABLED` is turned on.

### Verification scope

Source inspection against the audited revision; the reproduction above is proposed, not executed. No production, billing-provider or live-data access.
```

2026-09-24 复核后英文稿改三处：去掉 only reachable route 并点明管理员账单接口也消费权益列表；泄露改为条件性风险；补固定提交源码链接，验证边界改为「源码核对加建议的离线复现」，不写成已执行 Moto。
