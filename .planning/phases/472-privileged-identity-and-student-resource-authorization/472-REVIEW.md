---
phase: 472-privileged-identity-and-student-resource-authorization
reviewed: 2026-07-15T03:00:00Z
status: issues_found
depth: standard
files_reviewed: 78
files_reviewed_list:
  - docs/security/client-error-actions.json
  - docs/security/phase-472-evidence.md
  - docs/security/route-authorization-inventory.json
  - docs/security/tutor-term-allowlist.json
  - scripts/check_teacher_terminology.py
  - scripts/generate_route_authorization_inventory.py
  - scripts/provision_production_admin.py
  - scripts/reconcile_privileged_identities.py
  - src/stoa/config.py
  - src/stoa/db/repositories/ai_teacher_tools_repo.py
  - src/stoa/db/repositories/capability_repo.py
  - src/stoa/db/repositories/identity_repo.py
  - src/stoa/db/repositories/privileged_identity_repo.py
  - src/stoa/db/repositories/question_repo.py
  - src/stoa/db/repositories/security_audit_repo.py
  - src/stoa/db/repositories/teacher_application_repo.py
  - src/stoa/db/repositories/user_repo.py
  - src/stoa/deps.py
  - src/stoa/main.py
  - src/stoa/models/question.py
  - src/stoa/models/user.py
  - src/stoa/routers/adaptive.py
  - src/stoa/routers/admin.py
  - src/stoa/routers/auth.py
  - src/stoa/routers/conversations.py
  - src/stoa/routers/notifications.py
  - src/stoa/routers/parents.py
  - src/stoa/routers/practice.py
  - src/stoa/routers/questions.py
  - src/stoa/routers/students.py
  - src/stoa/routers/teacher_applications.py
  - src/stoa/routers/teachers.py
  - src/stoa/security/admin_authorization.py
  - src/stoa/security/authorization.py
  - src/stoa/security/client_error_actions.py
  - src/stoa/security/errors.py
  - src/stoa/security/events.py
  - src/stoa/security/identity.py
  - src/stoa/security/identity_resolution.py
  - src/stoa/security/jwks.py
  - src/stoa/security/reconciliation.py
  - src/stoa/security/route_authorization.py
  - src/stoa/security/route_inventory.py
  - src/stoa/security/tokens.py
  - src/stoa/services/adaptive_learning_service.py
  - src/stoa/services/ai_teacher_tools_service.py
  - src/stoa/services/curriculum_ops_service.py
  - src/stoa/services/moderation_service.py
  - src/stoa/services/notification_service.py
  - src/stoa/services/privileged_identity_service.py
  - src/stoa/services/teacher_application_service.py
  - src/stoa/services/teacher_assistance_service.py
  - src/stoa/services/teacher_dispatch_service.py
  - tests/actor_helpers.py
  - tests/security/conftest.py
  - tests/test_adaptive_learning.py
  - tests/test_admin_authorization.py
  - tests/test_admin_report_ops.py
  - tests/test_ai_operations.py
  - tests/test_ai_teacher_tools.py
  - tests/test_auth_security.py
  - tests/test_conversations.py
  - tests/test_curriculum_ops.py
  - tests/test_identity_authorization.py
  - tests/test_notifications.py
  - tests/test_parent_children.py
  - tests/test_practice.py
  - tests/test_privileged_identity_reconciliation.py
  - tests/test_provision_production_admin.py
  - tests/test_questions.py
  - tests/test_route_authorization_inventory.py
  - tests/test_student_authorization_matrix.py
  - tests/test_students.py
  - tests/test_teacher_availability.py
  - tests/test_teacher_dispatch.py
  - tests/test_teacher_onboarding.py
  - tests/test_teacher_reply_sla.py
  - tests/test_teacher_terminology_gate.py
findings:
  critical: 3
  warning: 4
  info: 0
  total: 7
---

# Phase 472: Code Review Report

**Reviewed:** 2026-07-15T03:00:00Z  
**Depth:** standard  
**Files Reviewed:** 78  
**Status:** issues_found

## Narrative Findings (AI reviewer)

## Summary

本次审查覆盖 Phase 472 SUMMARY 指定的 78 个实现、契约、证据与测试文件，重点追踪了 Cognito token 到稳定业务身份的绑定、能力授权的新鲜读取、学生资源策略、管理员路由分类、教师任务接管、特权身份对账和安全事件投影。当前聚焦门禁可通过，但存在 3 个发布阻断问题和 4 个警告：新注册的学生/家长没有建立严格解析所必需的身份绑定；教师接管是非条件写入；异常身份对账保留仍为 active 的能力授权；此外，路由清单、授权审计和公开认证错误边界仍有缺口。

已复跑 Phase 472 选定授权套件，371 项通过；完整 459 项 Phase 472 聚焦命令也已启动验证。已知全套 23 个 Phase 474 严格生产 Settings fixture 失败未计为本阶段回归。

## Critical Issues

### CR-01: 公共注册没有创建严格身份解析所必需的 `(issuer, sub) -> user_id` 绑定

**Severity:** Critical  
**File:** `src/stoa/routers/auth.py:329-426`  
**Impact:** `/auth/register` 从 Cognito 得到 `UserSub` 并写入本地学生/家长 profile，但整个注册/确认流程没有调用 `identity_repo.create_identity_binding`。Phase 472 的所有受保护请求随后在 `resolve_actor()` 中先读取绑定；缺失绑定会固定返回 `identity_conflict`。因此新注册并完成邮箱验证的学生和家长仍无法访问任何受保护产品资源，这是新身份模型对主注册路径的确定性功能阻断。

**Evidence:** `auth.py:329` 已取得 Cognito `UserSub`，`auth.py:396-426` 只构造并写入 profile；仓库全局调用检索显示 `create_identity_binding()` 只用于教师激活和管理员配置。与此同时，`src/stoa/security/identity.py:95-100` 对不存在的绑定直接拒绝。现有注册测试只断言 profile/关系状态，没有覆盖“注册 → 确认 → 使用真实绑定解析 Actor”的正向链路。

**Actionable fix:** 在公共注册生命周期中以配置的规范 issuer、Cognito `UserSub` 和稳定 `user_id` 条件创建绑定。保持 deny-first：profile 在邮箱确认前仍为非 active；绑定/profile/inventory 任一步失败时返回安全的可恢复错误并保留可重试命令。增加学生和家长的端到端测试，证明确认后 `get_actor` 成功，并覆盖绑定冲突、部分写入重试和重复确认。

### CR-02: 教师接管在授权读取后执行无条件写入，两个并发接管都可能成功

**Severity:** Critical  
**File:** `src/stoa/routers/teachers.py:171-219`  
**Impact:** 两名教师可以同时读取同一条 `escalated`/未分派问题并分别通过 CLAIM 策略，然后都调用无条件 `update_status()`、创建各自 session 并发送接管通知。最后写入者覆盖 `teacher_id/session_id`，但先写者仍收到成功响应并留下孤立 session 与错误通知。这破坏单一当前教师的不变量，并形成典型授权检查到效果执行之间的 TOCTOU。

**Evidence:** `teachers.py:182-191` 仅检查已加载快照，`teachers.py:195-205` 调用无条件更新；对应 `src/stoa/db/repositories/question_repo.py:86-99` 没有 `ConditionExpression`。相邻的自动 dispatch 路径已在 `teacher_dispatch_service.py:140-164` 使用条件更新，说明该竞态在接管路径中是不一致遗漏。`tests/test_teacher_dispatch.py:199-233` 只验证单请求成功/他人拒绝，没有并发 claim-conflict 测试。

**Actionable fix:** 将接管改为条件状态转换，条件至少绑定当前 `status=escalated`、dispatch 状态、允许的 `dispatched_teacher_id` 和未过期 deadline；条件失败返回安全的 409。最好用 DynamoDB transaction 同时写 question 与唯一 session（或先条件 claim，再以条件/幂等键创建 session），通知仅在 claim 成功后发出。增加两个教师共享同一旧快照时仅一方成功的测试。

### CR-03: 对账只撤销“格式无效”授权，冲突身份的有效授权会在账户恢复后自动复活

**Severity:** Critical  
**File:** `src/stoa/security/reconciliation.py:151-195`  
**Impact:** 对于缺少批准、重复绑定、多角色或 provider/local 不匹配的身份，对账会暂停账户并移除组，但只把 `invalid_grants` 加入 `remove_grant`。状态为 active、版本大于零且字段非空的授权会原样保留。管理员之后显式恢复账户/组时，这些旧授权立即重新进入 `resolve_actor()`，无需单独批准 capability grant，形成 reconciliation 后的自动再提升，违反 D-24 的“恢复与授权分别显式批准”。

**Evidence:** `reconciliation.py:151-154` 把撤销集合限制为格式/状态无效授权，`reconciliation.py:188-189` 只为该集合生成 `remove_grant`，`reconciliation.py:195` 也保留其余 grantCount。`tests/test_privileged_identity_reconciliation.py:60-83` 只覆盖一个 version=0 的无效授权，没有“missing approval + active valid grant”或恢复后授权复活的控制。

**Actionable fix:** 任何非 `exact_approved_active_match` 的特权身份都应自动撤销/隔离全部当前授权，或把授权移入不可生效的 quarantined 状态；恢复账户不能恢复旧授权，必须由 active `admin_identity_manager` 逐项、带 scope/reason/version 重新批准。扩展 snapshot 以校验 capability allowlist、effective/expiry 和 grant ownership，并增加异常身份携带有效全局授权的回归测试。

## Warnings

### WR-01: 路由清单没有递归收集依赖参数，嵌套依赖中的敏感 ID 可被漏报

**Severity:** Warning  
**File:** `src/stoa/security/route_inventory.py:124-131`  
**Impact:** 清单虽然递归遍历 dependency tree 读取授权元数据，但 identifier 检测只读取根 `route.dependant` 的 path/query/body 参数。若 `student_id`、`event_id` 或 token reference 仅由嵌套 dependency 声明，清单会将 identifiers 记录为空；配合 explicit public/global 标记可绕过 identifier-policy 检查，使发布清单对新增敏感参数失明。

**Evidence:** 用当前实现构造 `GET /probe`（endpoint 标记 public，嵌套 `Depends` 声明 `student_id: Query`）时，`inventory_projection()` 输出 `identifiers: []`、`sensitive: false`。`tests/test_route_authorization_inventory.py:72-95` 仅覆盖 endpoint 自身的 path/body 参数，没有 dependency 参数变异测试。证据文档第 16 行声称使用递归 dependency inspection，但该递归目前只覆盖分类元数据。

**Actionable fix:** 在 `_route_identifiers()` 中遍历 `_walk_dependants(route.dependant)`，聚合每个 dependant 的 path/query/body 参数，并递归处理 Pydantic 容器/union/Annotated。增加 nested dependency 的 student/event/token identifier 变异测试；对 public/safe-public 的敏感 ID 也应要求明确、窄化的公开资源类型，而不是无条件跳过。

### WR-02: 授权决策生成了安全事件但从未持久化，拒绝、探测与敏感允许均无审计证据

**Severity:** Warning  
**File:** `src/stoa/security/authorization.py:468-481`  
**Impact:** 策略构造了包含 actor/resource/action/purpose/result/correlation 的 allowlisted event，但调用者仅检查 `decision.allowed`，从未调用 `security_audit_repo.append_authorization_event()`。因此跨学生尝试、资源枚举、敏感允许和重复 probe 没有 D-32 要求的持久审计/聚合告警，事故调查证据与检测能力缺失。

**Evidence:** `authorize_and_resolve()` 在 `authorization.py:587-592` 取得 decision 后直接返回或抛错；源码全局检索中，`append_authorization_event()` 除 repository 定义和 break-glass helper 外没有生产调用。现有测试只验证事件投影和 repository helper，未验证一次真实拒绝会产生审计记录，也未验证审计故障策略。

**Actionable fix:** 向授权管线注入 audit sink，在安全拒绝和敏感允许路径写入稳定 event_id/correlation ID；重复探测使用有界聚合。明确失败语义：拒绝本身仍应保持拒绝，敏感允许若审计是强制控制则在审计不可用时 fail closed 为安全 503。增加真实依赖路径的 persisted-event、redaction、重复聚合和 audit-outage 测试。

### WR-03: 公开认证端点把 Cognito 内部错误代码直接返回给客户端

**Severity:** Warning  
**File:** `src/stoa/routers/auth.py:363,468,579,687,748,782,848,876`  
**Impact:** 未被显式映射的 provider 错误以 `Cognito error: {code}` 返回，暴露身份提供商实现和故障类型，并绕过 Phase 472 的统一安全错误 `{code,message,correlationId}` 契约。不同配置/用户状态可由公开端点探测，且客户端无法按 D-29/D-31 的稳定动作处理。

**Evidence:** register、login、verification、password reset、refresh、logout 均存在相同 fallback；这些 fallback 没有使用 `safe_error_response()`，也没有 correlation ID。聚焦测试只覆盖已知 provider code，不覆盖未知 code 的响应投影与 canary 泄漏。

**Actionable fix:** 将 provider exception 仅写入经脱敏的内部 telemetry，公开响应统一映射为稳定的 `identity_provider_unavailable`（临时依赖错误）或 `invalid_token/authentication_required`，带 correlation ID 和适当 `Retry-After`。增加未知 provider code/message/canary 不出现在响应中的参数化测试。

### WR-04: 登录成功后仍按 email 选择本地 profile，绕过稳定 subject 绑定用于响应/生命周期判断

**Severity:** Warning  
**File:** `src/stoa/routers/auth.py:470-489`  
**Impact:** Cognito 已返回 access token 后，登录路径通过最终一致 GSI 的 email `Limit=1` 获取任意一个本地 profile，并据此决定是否返回 token以及构造姓名、角色和账户状态。重复/大小写漂移/旧 profile 可导致披露另一业务身份的元数据，或让已撤销主体因同邮箱 active profile 而收到 token（后续受保护调用虽会由严格绑定拒绝）。这与 D-19“email 永不作为安全身份 fallback”冲突。

**Evidence:** `auth.py:473` 调用 `get_user_by_email()`；`src/stoa/db/repositories/user_repo.py:20-28` 使用 GSI `Limit=1` 且不做唯一性/subject 校验。严格请求路径已经提供 `(issuer, sub)` 绑定解析，但登录响应未复用它。现有测试没有两个同邮箱 profile 或 token subject/profile 不一致的负向控制。

**Actionable fix:** 验证刚签发的 access token并通过 `(issuer, sub)` 一致读取绑定/profile/status，只有该 Actor 可授权时才返回业务用户响应；email 只用于凭据提交，不参与本地身份选择。对绑定缺失/重复、email 重复、subject 不匹配和撤销账户增加测试。

---

_Reviewed: 2026-07-15T03:00:00Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
