---
phase: 475-transactional-usage-assignment-and-relationship-consistency
reviewed: 2026-07-22T02:04:46Z
depth: standard
files_reviewed: 50
files_reviewed_list:
  - docs/security/phase-475-evidence-results.json
  - docs/security/phase-475-evidence.md
  - scripts/verify_phase475.py
  - src/stoa/db/repositories/account_deletion_repo.py
  - src/stoa/db/repositories/notification_repo.py
  - src/stoa/db/repositories/practice_repo.py
  - src/stoa/db/repositories/question_repo.py
  - src/stoa/db/repositories/question_submission_repo.py
  - src/stoa/db/repositories/user_repo.py
  - src/stoa/jobs/reconcile_question_submissions.py
  - src/stoa/models/practice.py
  - src/stoa/models/question.py
  - src/stoa/routers/admin.py
  - src/stoa/routers/auth.py
  - src/stoa/routers/practice.py
  - src/stoa/routers/questions.py
  - src/stoa/routers/teachers.py
  - src/stoa/security/authorization.py
  - src/stoa/services/account_deletion_service.py
  - src/stoa/services/notification_service.py
  - src/stoa/services/practice_projection_service.py
  - src/stoa/services/rate_limit.py
  - src/stoa/services/subscription_service.py
  - src/stoa/services/usage_ledger_service.py
  - tests/test_admin_authorization.py
  - tests/test_auth_account_lifecycle.py
  - tests/test_conversations.py
  - tests/test_curriculum_analytics.py
  - tests/test_phase473_account_deletion.py
  - tests/test_phase473_account_deletion_claim_fencing.py
  - tests/test_phase473_delivery_intent_recovery.py
  - tests/test_phase473_notification_deletion.py
  - tests/test_phase475_completed_deletion_replay.py
  - tests/test_phase475_delivery_begin.py
  - tests/test_phase475_evidence_verifier.py
  - tests/test_phase475_mistake_answer.py
  - tests/test_phase475_parent_binding_reconciliation.py
  - tests/test_phase475_parent_binding_transaction.py
  - tests/test_phase475_profile_version_cas.py
  - tests/test_phase475_question_admission.py
  - tests/test_phase475_question_reconciliation.py
  - tests/test_phase475_question_replay.py
  - tests/test_phase475_rate_limit.py
  - tests/test_phase475_teacher_takeover.py
  - tests/test_phase475_teacher_takeover_effect.py
  - tests/test_practice.py
  - tests/test_questions.py
  - tests/test_subscription_operations.py
  - tests/test_teacher_dispatch.py
  - tests/test_teacher_reply_sla.py
findings:
  critical: 10
  warning: 4
  info: 0
  total: 14
status: issues_found
---

# Phase 475: Code Review Report

**Reviewed:** 2026-07-22T02:04:46Z
**Depth:** standard
**Files Reviewed:** 50
**Status:** issues_found

## Summary

对 50 个运行时、证据与测试文件进行了标准深度对抗性审查。事务准入本身有明显加固，但生产调用链仍存在 10 个必须在发布前修复的问题：外部效果成功后的持久化失败不可恢复、问题状态写入可覆盖教师接管、关系事务缺少父账户栅栏且可复活失效关系、回放快路径绕过完整性/所有权校验、终态补偿没有生产状态生成器、回放收据不稳定，以及删除发现遗漏跨账户身份字段。现有测试大量使用路由级 monkeypatch 或直接构造不可由生产代码生成的状态，因此没有覆盖这些失败窗口。

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]: OCR/AI 已成功但状态写入失败时，结果永久丢失且相同键无法恢复

**File:** `src/stoa/routers/questions.py:475-534`

**Issue:** OCR 和 AI provider 调用与 `question_repo.update_status()` 位于同一个宽泛的 `try` 中。provider 已成功后若 DynamoDB 更新超时或条件失败，代码把它当成 provider 失败并返回/吞掉异常；命令已经以 `processing` 准入。相同幂等键的后续请求在 324-349 行直接返回已存问题，不会再次执行 OCR/AI，也没有持久化 provider 结果可供补写。因此一次部分失败会让 OCR 永久停在 `processing`，或让已生成的 AI 答案永久丢失。

**Fix:** 在 provider 调用前持久化 effect intent，在 provider 成功后保存可重放的结果/收据，并用一个包含问题版本和命令版本条件的事务完成问题与命令；将 provider 失败、提交前依赖失败、提交结果未知分别建模。为“provider 成功、状态事务超时/失败、同键重试”添加真实仓储边界测试。

### CR-02 [BLOCKER]: 问题回放快路径绕过命令模式和所有权校验，可返回其他学生的问题

**File:** `src/stoa/routers/questions.py:324-349`

**Issue:** 快路径只比较 `fingerprint`，随后信任命令中的 `question_id` 并调用 `question_repo.get_question()`。它没有验证命令的 `student_id`、`idempotency_key`、`entity_type`、`schema_version`、状态，也没有验证加载问题的 `student_id == actor.user_id`。仓储中的 `_classify_command()` 本来做了大部分命令校验，但该路径绕过了它。损坏、旧模式或误写的命令行可把一个学生的回放指向另一学生的问题并返回私有内容；附件预留失败后的 360-380 行重复了同一问题。

**Fix:** 所有回放统一调用仓储的严格分类入口；加载问题后再次核对学生、问题 ID、命令指纹和账户 generation。任何不一致均返回不可用/冲突，绝不能投影问题内容。

### CR-03 [BLOCKER]: 普通问题状态写入没有版本 CAS，可覆盖已提交的教师接管事务

**File:** `src/stoa/db/repositories/question_repo.py:588-640`

**Issue:** `build_question_update_transaction()` 的默认条件只有行存在和 `student_id` 相等，更新也不递增 `version`。AI 回答、OCR、升级、反馈和教师回复都走 `update_status()`。教师接管事务虽然校验并递增版本，但并发的普通更新不校验版本：例如接管提交为 `teacher_active` 后，一个稍晚到达的 AI 更新仍可把状态改回 `ai_answered`，同时保留已创建的 session，产生孤儿会话和授权状态不一致。

**Fix:** 让每个问题更新读取并条件匹配当前版本，同时原子递增版本；状态转换还应匹配允许的来源状态。条件失败必须重新读取并分类，不能盲目覆盖。增加 AI 完成/升级/接管并发交错测试。

### CR-04 [BLOCKER]: 教师接管事务没有原子验证教师账户，授权检查存在 TOCTOU

**File:** `src/stoa/db/repositories/question_repo.py:395-459`

**Issue:** 路由授权阶段读取了教师账户，但最终事务只包含学生账户 fence、问题更新和 session Put。教师可在授权完成与提交之间被停用或进入删除流程，事务仍会将其写为当前教师并创建会话。仓储函数还接受任意 `teacher_id`，自身没有教师角色/活跃状态条件。

**Fix:** 在同一 DynamoDB 事务中加入教师 active fence 和教师 PROFILE 的角色/状态/版本条件；把授权阶段观察到的教师 generation/version 作为不透明 claim 传入仓储。教师条件丢失应返回明确的 claim-lost/retryable 结果。

### CR-05 [BLOCKER]: 父子关系事务只栅栏学生账户，能与父账户删除并发写入残留关系

**File:** `src/stoa/db/repositories/user_repo.py:460-492`

**Issue:** 关系事务写父分区正向行、学生分区反向行和学生 PROFILE，但只包含学生 active fence。父账户可在快照后进入删除/完成删除，关系事务仍可成功，在已删除父账户名下创建新的正向关系，并重新引入跨账户身份数据。

**Fix:** 事务同时条件检查父、学生两个账户 fence，并检查父 PROFILE 为 active parent、学生 PROFILE 为 active student；预览/提交绑定双方的 generation/version。任一方状态变化均应失败关闭。

### CR-06 [BLOCKER]: 相同版本的已撤销关系可被普通“重放”重新激活

**File:** `src/stoa/db/repositories/user_repo.py:433-446`

**Issue:** 已有关系行的条件只校验 parent/student/relationship/version，随后无条件 `SET status=:status, source=:source, actor=:actor`。`_parent_relationship_conflicts()` 又不比较状态。因此同一 pair/version 的 `revoked`、`inactive` 或其他非活跃行不会被判定冲突，注册调用可以在不递增版本、没有显式授权转换的情况下把它改回 `active`，恢复父级访问所需的两条正式关系。

**Fix:** 创建/幂等重放仅允许不存在或所有不可变字段及状态完全相同；状态迁移使用独立的授权 API，要求预期旧状态和版本并递增版本。对 revoked→active、两侧状态不一致和并发撤销增加测试。

### CR-07 [BLOCKER]: 终态配额补偿没有生产状态生成路径，测试手工构造了不可达状态

**File:** `src/stoa/db/repositories/question_submission_repo.py:627-637`

**Issue:** 补偿只在命令已经是 `terminal_failed` 且带 `terminal_failure_code`/`terminal_failure_proven_at` 时触发；审查范围内没有任何生产代码写入这些字段或状态。`tests/test_phase475_question_reconciliation.py:44-69` 直接在 fake 中播种该状态，所以“精确一次反转”测试只证明了后半段算法，未证明真实失败能进入补偿。实际 AI/OCR 失败只留下永久 `processing` 并继续占用配额。

**Fix:** 实现经过分类的终态转换：用命令版本、问题版本、指纹和 provider 证据做条件事务，写入 `terminal_failed` 证明；随后由可发现/可调度的协调器执行补偿。测试必须从真实路由/服务失败开始，经过真实终态写入再验证反转，而不是直接构造终态行。

### CR-08 [BLOCKER]: 原始客户端幂等键被用作主键、账本字段和作业输出，破坏隐私边界

**File:** `src/stoa/db/repositories/question_submission_repo.py:146-152`

**Issue:** `SubmitQuestionRequest` 允许任意 8-200 字符字符串作为幂等键；该原值进入 DynamoDB SK、命令 `command_id`、usage ledger 的 SK/event_id/字段，并由协调作业作为 `commandId` 输出（`src/stoa/jobs/reconcile_question_submissions.py:65-74`）。调用方可能把邮箱、题目或其他私有文本误放入键中，随后这些值进入运维输出、日志和长期账本；当前 denylist 测试只检查固定 canary，无法保证任意用户值不泄漏。

**Fix:** 在 API 边界对客户端键做带域分隔的 HMAC/哈希，持久化和输出只使用不透明摘要；原键不写数据库、不进入日志。若需冲突诊断，仅保留摘要和 payload fingerprint。

### CR-09 [BLOCKER]: 速率限制回放返回当前全局计数，而非该操作的稳定准入收据

**File:** `src/stoa/services/rate_limit.py:271-298`

**Issue:** 操作行没有保存准入时的 `counter_value_after`，回放时 `_classify_operation()` 接收的是刚读取的当前 counter。若操作 A 在 count=1 准入，操作 B 后把 count 推到 2，再回放 A，A 的收据从 1 变成 2。幂等响应和下游 usage 元数据因此依赖其他请求的时序，无法作为该逻辑操作的稳定证据。

**Fix:** 在同一事务写入操作行时保存该操作的预期 `counter_value_after` 和 expiry/limit 快照；回放严格投影操作行中的收据。增加“A、B 准入后回放 A 仍返回 A 原始计数”的测试。

### CR-10 [BLOCKER]: 删除发现不识别 `parent_id`/`teacher_id`/`actor_id`，跨账户身份数据可在删除后残留

**File:** `src/stoa/db/repositories/account_deletion_repo.py:1624-1655`

**Issue:** 通用私有行发现 `_targets_user()` 检查 owner/student/user/child 等字段，却遗漏 `parent_id`、`teacher_id` 和 `actor_id`。Phase 475 的正式关系行包含 `parent_id`，教师 session/question/通知元数据包含 `teacher_id`/`actor_id`。删除父账户或教师账户时，这些由其他账户拥有的行不会进入后续 scrub 分支，身份关联可长期残留；分支 predicate 再完整也无法处理从未被发现的行。

**Fix:** 为跨账户身份建立显式反向索引/删除清单，并在删除命令中逐项 CAS scrub；至少扩展所有权发现和测试矩阵，覆盖 parent 正/反关系、teacher session/question、通知 actor/metadata，并验证两次干净 epoch 后不再存在原始身份值。

## Warnings

### WR-01 [WARNING]: 未提供幂等键时，服务端随机问题 ID 无法支持丢失响应重试

**File:** `src/stoa/routers/questions.py:306-310`

**Issue:** `idempotencyKey` 在模型中是可选的；缺省时键来自本次请求刚生成的 UUID。客户端在响应丢失后无法知道该 UUID，重复相同请求会生成新键、新问题并再次占用配额。文档所称“稳定幂等键”只对显式提供键的调用成立。

**Fix:** 对需要重试安全的 POST 强制客户端幂等键，或使用客户端可重建且具防碰撞边界的请求标识；明确迁移旧客户端，并添加无响应重试测试。

### WR-02 [WARNING]: targeted mypy 可在工具崩溃/配置失败时仍发布 PASS

**File:** `scripts/verify_phase475.py:413-442`

**Issue:** 状态只取决于能否从输出解析出“落在 changed line 的 error”；`completed.returncode` 仅记录、不参与 PASS。若 mypy 可执行文件失败、配置错误或输出格式变化导致没有匹配行，即使退出码非零也会得到 PASS。现有测试只覆盖标准诊断文本，没有覆盖 fatal/no-output 失败。

**Fix:** 明确允许的退出码与 mypy 完成摘要；非预期 stderr、无摘要、解析失败或工具异常必须失败。增加 returncode=2/无诊断、不可执行和配置错误用例。

### WR-03 [WARNING]: “immutable source snapshot” 静默忽略无法读取/已删除的变更文件

**File:** `scripts/verify_phase475.py:755-763`

**Issue:** `_source_snapshot()` 对 `git show candidate:path` 失败直接 `continue`，没有记录删除标记，也不校验快照条数等于 diff 范围。证据仍宣称记录了 immutable source snapshot，但删除文件或读取失败可以无声缺席。

**Fix:** 对非删除路径读取失败立即报错；对删除路径记录 base blob、删除标记和哈希；验证快照路径集合与标准化 diff 路径集合完全相等。

### WR-04 [WARNING]: 路由回放测试 monkeypatch 掉了实际事务和持久化失败窗口

**File:** `tests/test_phase475_question_replay.py:82-116`

**Issue:** 关键的丢失响应测试把 `admit_question_submission` 和 `question_repo.update_status` 都替换为内存赋值，因此不会执行 DynamoDB 条件、版本更新、命令完成，也无法模拟“provider 成功但持久化失败”。这使 CR-01/CR-03 在证据中仍被标为通过。

**Fix:** 使用能执行真实 transaction operation 的 fake，至少保留仓储实现不 mock；注入每个事务边界的 commit-before-timeout/conditional-failure，并断言同键重试恢复原始 durable result 且不重复 provider effect。

---

_Reviewed: 2026-07-22T02:04:46Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
