# E1 年级从准入限制改为讲解深度

Status: released
Blocked by: 
Decision: [票据 01](../issues/01-grade-as-depth-prompt.md)
GitHub: #19

## Delivers

超纲的同学科问题得到可理解的解释与类比，而不是被提示词引向拒答。

## Change

`src/stoa/services/ai_service.py` SYSTEM_PROMPT：第一句与 "too complex" 规则按票据 01 决议原文替换；其余规则、JSON 契约、语言指令不动。

## Acceptance

新测试捕获出站提示词：数学 Grade 6 "Was ist eine Ableitung?" 与物理 Grade 5 "Was ist Quantenphysik?" 不含 "ONLY answer questions related to {subject} at {grade} level" 且含 "never to decide whether a question deserves an answer"；年级内普通题、跨学科拒答对照不变。

## Poison

把第一句改回旧写法 → 两条新测试必红。

## Commit

单独一个提交。上线后用两道德语原题各问一次做冒烟，不推断拒答率。

## Verification

2026-09-24 地图会话核查，提交 `04fd9737`。新增 4 条（两道超纲题参数化、年级内对照、跨学科对照）全部通过。投毒：把第一句改回旧写法 → 4 failed / 22 passed。与票据 01 决议逐句一致；step-by-step 与 JSON 契约未动。

全量离线回归（排除依赖相邻 infra 根目录的两个 release-gate 文件）3541 passed / 0 failed；`test_formal_release_gate.py` 的一条失败在这五个提交之前的 a015a444 上同样失败，属既有 infra 根目录问题。ruff 对改动文件全部通过；mypy 报错都在未改动的文件里。与远端 origin/main 新增的 4 个提交（b7b1b4f8…ef0827c9）在临时 worktree 里合并无冲突，重叠文件相关 308 条测试通过。五个提交**尚未推送**，未部署。

## Released

2026-09-24 18:48Z 推送 653821db，"Deploy Backend to Production" run 36043828300 全部步骤 success；18:55Z `stoa-api` production 别名 → v115、`stoa-account-deletion` → v26（同一 CodeSha256 `DyCi5IIL…`），SSO 只读核对（账号 562923011260、AWSReservedSSO 角色）。
