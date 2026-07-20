# Demo Video Script

Target length: **2:40–2:55**. The public YouTube video must remain under three minutes and include
audio explaining both the working project and the use of Codex and GPT-5.6.

Do not record until the integrated demo path and test identities are stable.

## 0:00–0:15 — Problem

**Visual:** STOA title, then a student question screen.

**Narration:**

> AI tutors can answer questions. The harder problem is making them safe enough for real
> students. STOA Safe Learning Layer protects student work, keeps practice answers hidden, and
> limits human-teacher access without removing the human safety net.

## 0:15–0:35 — Honest Build Week scope

**Visual:** Simple before/after diagram or Git timeline beginning at `de3bf1e`.

**Narration:**

> STOA existed before Build Week. During the challenge, we used Codex and GPT-5.6 to build and
> verify this trust layer: centralized authorization, private upload handling, answer-safe
> practice, retry-safe state transitions, and deterministic release evidence.

Replace the GPT-5.6 statement if the required session evidence cannot be verified.

## 0:35–1:10 — Student upload and AI-assisted question

**Visual:** Log in as the demo student, upload a safe image, submit a question, and show the result.

**Narration:**

> The student receives an opaque upload intent. STOA validates the actual bytes, binds the exact
> immutable file to its owner, permits one-time use, and only then allows OCR and question
> creation. The client never receives a storage key, provider URL, multipart identifier, or raw
> OCR text.

## 1:10–1:35 — Adversarial privacy check

**Visual:** Use a prepared second-student request or safe test harness to request the first
student's resource; show the same concealed response as a random ID. Do not expose real student
data, tokens, storage coordinates, or raw logs.

**Narration:**

> A valid identifier is not authorization. An unrelated student, parent, or teacher cannot use
> guessed or known IDs to discover the resource. The policy evaluates fresh owner, relationship,
> assignment, and capability facts before any effect.

## 1:35–2:00 — Practice without answer leakage

**Visual:** Open a practice challenge and inspect the answer-free preview. Submit an attempt, then
show the answer and explanation.

**Narration:**

> Before an attempt, the response model cannot contain the answer, explanation, or answer-derived
> feedback. STOA records the attempt first. Only a successful durable receipt can unlock the
> answer-bearing result.

## 2:00–2:20 — Human in the loop

**Visual:** Request teacher help, then switch to an assigned teacher test account and show the
bounded queue or response surface.

**Narration:**

> Students can escalate to a human. But the teacher role is not blanket access: only an active
> assignment or an exact capability exposes the required learning context.

## 2:20–2:42 — Codex/GPT-5.6 collaboration

**Visual:** Sanitized Codex session excerpt, challenge-period commit timeline, and test result.

**Narration template:**

> We used Codex with GPT-5.6 to `[OWNER INPUT: describe the verified core session]`. Codex helped
> us trace trust boundaries, implement conditional state transitions, generate adversarial tests,
> and verify legitimate and denied flows together. The submitted increment includes 493 commits
> after our pre-challenge baseline, with a focused privacy matrix and a 2,009-test full-suite
> verification at the cited candidate.

## 2:42–2:55 — Close

**Visual:** Student → Safe AI → Authorized Teacher → Parent loop.

**Narration:**

> STOA Safe Learning Layer makes AI tutoring more than a demo: private by construction,
> answer-safe, retry-safe, and still connected to a real human when the student needs one.

## Recording safeguards

- Use synthetic users and synthetic learning content only.
- Hide browser password managers, notifications, bookmarks, tokens, terminal secrets, AWS account
  identifiers, internal URLs, and personally identifiable information.
- Use English narration or provide complete English translation/subtitles for all content.
- Use only music, images, fonts, and trademarks that the entrant is authorized to publish.
- Keep the final uploaded video public on YouTube through the judging period.

