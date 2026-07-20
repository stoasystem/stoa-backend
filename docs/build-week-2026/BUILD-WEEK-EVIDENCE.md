# Build Week New-Work Evidence

## Eligibility boundary

STOA is a pre-existing project. The submission must claim only the meaningful extension built
after the challenge submission period opened.

- **Challenge submission period opened:** 2026-07-13 09:00 Pacific Time
- **Last repository commit before the challenge-period work:**
  `de3bf1e4133550e1c679bf611b026437336bd219`
- **First repository commit in the recorded challenge-period sequence:**
  `452134aa26c9f82b7b6265cd5dfd1d72ed20bc1b` at 2026-07-14 14:38:59 +02:00
- **Preparation-time HEAD:**
  `2017a6e858c2ddfeb9e75beda4096f5d40de0e58`
- **Commits after the pre-challenge baseline:** 493

The primary Codex `/feedback` session ID is
`019f60c5-f092-74e2-9c73-6f573e8eff1e`. Local session metadata records the model as
`gpt-5.6-sol`; the session began on 2026-07-14 and contains the majority of the authorization,
privacy, adversarial-testing, and deterministic-verification work described below.

## Submitted increment

### 1. Privileged identity and student-resource authorization

- Closed public privileged-registration and horizontal student-data access paths.
- Added issuer/client-bound token verification and authoritative actor resolution.
- Added versioned, scope-specific capabilities and deny-first teacher activation.
- Centralized owner, parent, assigned-teacher, and administrator resource policy.
- Generated a deterministic authorization inventory for 219 API operations.

Primary evidence:

- `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-VERIFICATION.md`
- `docs/security/route-authorization-inventory.json`
- `src/stoa/security/`

### 2. Student-content privacy and practice integrity

- Replaced storage-coordinate-bearing upload behavior with opaque owner-bound intents.
- Added bounded file validation, immutable promotion, one-time attachment use, and safe cleanup.
- Bound OCR and question creation to exact owner-resolved immutable bytes.
- Removed raw storage/OCR data from student question responses.
- Added answer-free practice projections and write-before-answer attempt receipts.
- Preserved a separate, authorized teacher/admin answer contract.

Primary evidence:

- `.planning/phases/473-student-content-privacy-and-practice-integrity/473-VERIFICATION.md`
- `src/stoa/services/attachment_service.py`
- `src/stoa/services/file_validation_service.py`
- `src/stoa/services/practice_projection_service.py`
- `tests/test_attachment_security.py`
- `tests/test_practice_privacy.py`

### 3. Deterministic verification and gated delivery

- Added clean, source-bound formal verification receipts.
- Added dependency and release-policy checks.
- Bound backend, Web, and infrastructure source identities into release evidence.
- Recorded two admitted Linux formal passes without representing production deployment as run.

Primary evidence:

- `evidence/phase-474/linux-formal-admission.json`
- `evidence/phase-474/linux-formal-run-1.json`
- `evidence/phase-474/linux-formal-run-2.json`
- `evidence/phase-474/final-source-handoff.json`

## Reproducible Git evidence

Run from the repository root:

```bash
git log --reverse \
  de3bf1e4133550e1c679bf611b026437336bd219..HEAD \
  --date=iso-strict \
  --pretty='format:%H%x09%ad%x09%s'

git diff --stat \
  de3bf1e4133550e1c679bf611b026437336bd219..HEAD
```

## Claims that must remain qualified

- STOA as a whole was not created during Build Week.
- Current evidence demonstrates extensive local and formal verification; it does not prove that
  every external provider or production path has been exercised.
- The native/mobile product is not the submitted working surface.
- The submission must not claim OpenAI as the runtime AI provider unless that integration is
  actually added and demonstrated.
- GPT-5.6 was used as the Codex engineering model for the submitted increment; STOA's documented
  runtime AI-provider boundary remains AWS Bedrock.
