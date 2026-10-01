# 把 B-2 建成 GitHub issue

Labels: wayfinder:task
Type: task
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 05
GitHub: [#22](https://github.com/stoasystem/stoa-backend/issues/22)

## Question

用票据 05 决议给出的正文，在 stoasystem/stoa-backend 建一条 issue，标题沿用 `[P1] ...` 前缀与审计 issue 的结构（Source、Reproduction、Expected、Verification scope）。建之前先查重（`gh issue list --search`），建之后直接 GET 回读核对标题与正文。对外动作，执行前向用户确认一次。

答案记录：issue 编号与链接，供地图 Notes 与票据 05 引用。

## Comments

2026-09-24：票据 05 已决议并给出英文正文稿，本票据进入 frontier。发布前仍需用户明确一句「发」。

2026-09-24：英文稿已按复核改三处（见票据 05 Answer）。仍等用户一句「发」。

## Answer

2026-09-24 用户确认「按稿发布」。查重（`entitlement child`、`_active_child_ids`、`reverse revocation`）无结果；已建 [#22](https://github.com/stoasystem/stoa-backend/issues/22)，标题与正文按票据 05 英文稿原文，`gh issue view` 回读核对一致（仅末尾换行差异）。E5 提交已 amend 引用 #22（未推送）。
