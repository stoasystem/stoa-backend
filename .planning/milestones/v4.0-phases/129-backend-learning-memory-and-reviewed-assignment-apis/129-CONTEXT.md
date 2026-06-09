# Phase 129 Context: Backend Learning Memory And Reviewed Assignment APIs

**Milestone:** v4.0 Adaptive Learning Memory And Assignment
**Requirement:** ADAPT-02
**Status:** Complete

## Why This Phase Exists

Phase 129 turns the Phase 128 contract into backend behavior. The repo already has learning profile seeds, curriculum catalog/progress APIs, question history, practice mistakes, and reviewed AI teacher exercise drafts. This phase composes those signals into durable adaptive memory snapshots and reviewed assignment APIs.

## Product Scope

- Aggregate student memory from questions, feedback, curriculum progress, mistakes, and topic seeds.
- Persist per-student subject/topic memory snapshots in the existing DynamoDB single-table model.
- Return role-scoped memory views for students, parents, tutors/teachers, and admins.
- Create reviewed assignments from curriculum exercises or accepted AI exercise drafts.
- Let students list, start, complete, and skip assignments while preserving progress compatibility.

## Constraints

- Reuse the existing DynamoDB table; do not introduce a new table or GSI.
- Keep generated AI exercise drafts review-before-use.
- Do not claim fully autonomous tutoring or assignment decisions.
- Parent-visible data must remain ownership-checked and hide internal/debug evidence.

