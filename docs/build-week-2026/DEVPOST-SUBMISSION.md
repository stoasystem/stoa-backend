# Devpost Submission Draft

Everything below is draft copy. Replace every `[OWNER INPUT]` value and verify every factual
claim before submission.

## Project name

STOA Safe Learning Layer

## Tagline

Safe AI tutoring, with humans in the loop.

## Track

Education

## Short description

STOA Safe Learning Layer is a trust layer for AI-assisted education. It lets a student upload a
question, receive AI-supported help, practice without premature answer disclosure, and escalate
to an authorized human teacher—while preventing cross-student data access, unsafe upload reuse,
answer leakage, and stale or unauthorized teacher access.

## Inspiration

AI tutors are easy to prototype and hard to trust. A convincing demo can answer a question; a
real learning product must also protect minors' work, keep answers hidden until an attempt is
recorded, ensure that parents and teachers see only the students they are authorized to support,
and survive retries and partial failures without duplicating or leaking data.

STOA already existed as a broader learning platform before Build Week. During the challenge, we
used Codex to focus on the less visible but essential problem: turning an AI tutoring workflow
into a defensible, testable learning boundary.

## What it does

- Accepts bounded student question uploads through opaque, owner-bound upload intents.
- Validates file type, content, size, lifecycle, and one-time use before OCR or question creation.
- Prevents one student, unrelated parent, or unassigned teacher from discovering another
  student's questions, conversations, uploads, or practice records.
- Keeps answers, explanations, and answer-derived feedback out of every pre-attempt student
  preview.
- Persists the student's attempt before returning answer-bearing feedback.
- Gives an assigned teacher a separate, explicit answer-bearing contract and supports human
  takeover without turning the teacher role into blanket student access.
- Uses idempotent commands, fenced leases, and deterministic release evidence to make retries and
  partial failures safe.

## How we built it

We used Codex as an engineering partner across audit, threat modeling, implementation, adversarial
test design, verification, and release hardening. The challenge-period work started from the
pre-existing commit `de3bf1e4133550e1c679bf611b026437336bd219` and is documented separately
from the older STOA product.

The implementation is a Python 3.12 FastAPI service deployed through AWS Lambda/API Gateway, with
DynamoDB and S3 persistence, Cognito identity, OCR, and an AI-provider boundary. The Build Week
increment introduced centralized actor/resource authorization, owner-bound immutable attachment
handling, answer-free practice projections, durable attempt receipts, privacy-safe telemetry,
and deterministic verification/release controls.

The primary Codex `/feedback` session ID is
`019f60c5-f092-74e2-9c73-6f573e8eff1e`. Local Codex session metadata records the model as
`gpt-5.6-sol`. In that session, GPT-5.6 supported authorization and privacy audits, threat-model
refinement, implementation, adversarial test design, Linux hermetic verification, and release
evidence for the submitted increment.

Do not state that STOA's runtime AI uses OpenAI unless that is actually implemented and shown.
The current repository documents an AWS Bedrock runtime boundary; the Build Week claim is about
using Codex and GPT-5.6 to build the submitted increment.

## Challenges we ran into

The hardest failures were not ordinary happy-path bugs. They appeared at trust boundaries:

- a valid identifier could not be allowed to become authorization;
- an upload retry could not create a second attachment or consume a different byte sequence;
- a failed attempt write could not be followed by an answer-bearing response;
- a stale deletion or delivery worker could not be allowed to record success;
- tests had to prove both legitimate student/parent/teacher flows and adversarial denials.

We addressed these with explicit actor and resource facts, conditional persistence, immutable
receipts, opaque storage coordinates, fenced work claims, typed response allowlists, and lower-
bound adversarial tests.

## Accomplishments that we're proud of

- A deterministic inventory covers 219 registered API method/path operations and their
  authorization dependencies.
- The challenge-period privacy milestone independently passed a 449-test focused matrix and a
  2,009-test full repository suite.
- Student practice previews are structurally answer-free; answers appear only after a durable
  attempt.
- Upload and OCR flows are owner-bound and expose no bucket, object key, provider URL, multipart
  ID, ETag, or raw OCR text to the client.
- Human support remains possible through narrow assignment/capability boundaries rather than
  unrestricted teacher access.

## What we learned

The biggest lesson was that trustworthy AI education is a systems problem, not only a prompting
problem. Model quality matters, but so do identity provenance, durable state transitions,
failure ordering, privacy-safe observability, and a product experience that makes human escalation
clear. Codex was especially valuable in exploring those boundaries, generating adversarial cases,
and repeatedly checking that fixes did not weaken legitimate flows.

## What's next

Next we will turn the verified backend trust layer into a fully integrated student, parent,
teacher, and administrator Web experience; complete approved non-production provider tests; and
measure whether the safer tutoring loop improves learning completion and teacher response time.
Production rollout and real-user activation remain separately approved operational decisions.

## Built with

Python, FastAPI, Pydantic, AWS Lambda, API Gateway, DynamoDB, S3, Cognito, OCR, Bedrock, pytest,
Codex, and GPT-5.6.

## Links

- **Public demo video:** `[OWNER INPUT — BLOCKER]`
- **Working demo:** `[OWNER INPUT — BLOCKER]`
- **Code repository:** https://github.com/stoasystem/stoa-backend
- **Additional project page:** `[OWNER INPUT, OPTIONAL]`
