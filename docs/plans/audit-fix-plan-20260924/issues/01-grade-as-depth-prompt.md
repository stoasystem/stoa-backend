# 年级应如何从准入限制改写为讲解深度（#19）

Labels: wayfinder:prototype
Type: prototype
Mode: HITL
Status: resolved
Parent: [审计 issue 修复决策地图](../map.md)
Blocked by: 
GitHub: [#19](https://github.com/stoasystem/stoa-backend/issues/19)

## Question

`src/stoa/services/ai_service.py` 的 SYSTEM_PROMPT 第一句写死 "You ONLY answer questions related to {subject} at {grade} level"，规则里又有"太复杂就建议老师介入"。产品口径已定：同学科超纲问题先用可理解的解释或类比回答，再视情况建议老师。

要决定的是提示词的具体写法，用一份可反应的草稿来定：
1. 学科边界一句怎么保留，年级一句改成"讲解深度与前置知识引导"该怎么措辞；"太复杂 → 老师"这条改成什么，才不会又变成拒答的出口。
2. `suggest_teacher` 字段在超纲问题上的期望值：先答再建议，还是只在情绪困扰或多轮仍不懂时才 true。
3. 回归测试断言什么：数学 Grade 6 问导数、物理 Grade 5 问量子物理的出站提示词不含准入限制句且含深度引导句；年级内普通题对照；跨学科拒答对照保持。提示词测试证明不了真实模型的拒答率，票据要写明这一边界。

产出：提示词草稿（作为资产链接）、测试断言清单。

## Answer

2026-09-24 用户按推荐决议并采纳独立复核的补充约束。

提示词按草稿改：第一句 "You ONLY answer questions related to {subject}. The student is in {grade}: use that to choose the depth of the explanation, the examples and the prerequisites you point to, never to decide whether a question deserves an answer."；"too complex → teacher" 改为 "If an in-subject question is far above {grade}, first give a short accessible explanation with one concrete example or analogy and name the ideas the student would need first; set suggest_teacher to true only if the student stays stuck after that, or shows emotional distress. Reject only questions outside {subject}."。「只讲步骤、不直接给最终答案」与其余规则不动。

验收：数学 Grade 6 导数、物理 Grade 5 量子两条出站提示词不含 "ONLY answer ... at {grade} level" 且含深度引导句；年级内普通题、跨学科拒答两条对照不变。边界：提示词测试证不了真实拒答率；上线后用两道德语原题各问一次只算冒烟检查，不据此推断整体。实施票据 [E1](../exec/E01-grade-as-depth-prompt.md)。
