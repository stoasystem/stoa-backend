# E6 把 B-2 建成 GitHub issue

Status: resolved
Blocked by: 无代码阻塞；发布需用户确认
Decision: [票据 06](../issues/06-file-entitlement-issue.md)
GitHub: [#22](https://github.com/stoasystem/stoa-backend/issues/22)

## Delivers

B-2 在 GitHub 有独立 issue，E5 的提交能引用它。

## Change

用票据 05 Answer 里的英文稿。先 `gh issue list --search` 查重，创建后 `gh issue view` 回读核对标题与正文。

## Acceptance

issue 可见、正文与稿一致；编号回填到票据 06 Answer、地图 Notes、E5 的 GitHub 字段。

## Poison

不适用。

## Commit

无代码提交。**对外动作，执行前用户需明确同意一次。**

## Verification

2026-09-24 地图会话核查。GitHub #22 已建（2026-09-24T15:27:52Z），正文与票据 05 Answer 里修改后的英文稿逐字一致（唯一差异是首行成了标题）；含管理员账单接口说明、条件性风险措辞、三处固定提交源码链接、「源码核对加建议的离线复现、未执行 Moto」的边界。未加 label，与 #2–#21 一致。E5 提交已 amend 为 129c91de，提交信息补上 #22，树与 6760f124 完全相同；amend 发生在推送之前，无害。
