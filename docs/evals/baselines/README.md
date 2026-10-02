# AI reply evaluation baselines

Reports written by `scripts/eval_ai_replies.py`; see stoasystem/stoa-backend#43.

## 2026-10-02 baseline and control

`ai-reply-eval-2026-10-02-baseline.json` and `ai-reply-eval-2026-10-02-control.json`:
the 40 questions under the current prompt, run twice.

- Language consistency, term violations, mixed replies and `suggest_teacher`
  are valid readings.
- **`refused` and `refusal_pct_out_of_syllabus` are not.** They were read with
  the rule fixed in `ea080459` and `dff79f8a`: a declining phrase counted only in
  a reply of fewer than two steps, and the phrases were too few. These reports
  keep only a 240-character excerpt of each reply, so they cannot be read again.
- The cost is at the script's reference rate (`cost_usd_at_first_party_rate`),
  not what AWS charged.

The refusal reading under the current prompt comes from the rerun of the same
day: the eight out-of-syllabus questions, their steps and answers kept in
`tests/fixtures/ai_reply_out_of_syllabus_2026-10-02.json`, read by hand as all
explained and by the fixed rule as 0/8 refused.
