# Judging Access Plan

The judges must be able to access a working project free of charge and without rebuilding it from
scratch. This file intentionally contains no credentials or secrets.

## Recommended judging surface

Provide one isolated, non-production demo environment containing synthetic data only.

- **Demo URL:** `[OWNER INPUT — BLOCKER]`
- **Availability window:** From submission through at least the end of judging
- **Region/latency note:** `[OWNER INPUT]`
- **Status page or fallback contact:** `[OWNER INPUT]`

## Required synthetic identities

Store credentials only in the private Devpost testing instructions, never in Git.

| Identity | Purpose | Ready |
| --- | --- | --- |
| Student A | Upload, question, practice, teacher-help happy path | `[ ]` |
| Student B | Cross-student concealment demonstration | `[ ]` |
| Parent A | Bound-child visibility and unrelated-child denial | `[ ]` |
| Teacher A | Assigned-teacher help and answer contract | `[ ]` |
| Optional admin | Read-only authorization/release evidence | `[ ]` |

## Repository access

- **Repository:** https://github.com/stoasystem/stoa-backend
- **Visibility:** `[OWNER INPUT: public or private — BLOCKER]`
- If private, invite both `testing@devpost.com` and `build-week-event@openai.com` before the
  deadline and verify access from an unaffiliated account.
- If public, confirm that the repository has an appropriate license and contains no secrets,
  personal data, proprietary third-party material, or internal-only evidence.

## Testing instructions template

1. Open `[DEMO URL]` in a current desktop browser.
2. Sign in as Student A using the credentials supplied privately in Devpost.
3. Open the question flow, upload the provided synthetic sample image, and submit it.
4. Open the practice flow. Observe that the preview contains no answer; submit an attempt and
   observe the persisted result, answer, and explanation.
5. Request teacher help.
6. In a separate browser profile, sign in as Teacher A and open the assigned request.
7. Optionally sign in as Student B and use the supplied safe test link to confirm that Student A's
   resource remains concealed.

## Demo acceptance gate

Before publishing access, verify all of the following against the exact submitted build:

- student login and session restoration;
- safe upload and question completion;
- answer-free practice preview and post-attempt result;
- teacher-help request and assigned-teacher view;
- synthetic cross-user denial;
- no placeholder, mock-backed success, or route interception in the judging path;
- no real student, parent, teacher, billing, or production data;
- no destructive admin, billing, bulk notification, or production operations available to judges;
- credentials remain valid through judging and can be rotated immediately afterward.

## Fallback

If an integrated Web demo cannot pass this gate before the deadline, do not represent it as
working. A backend-only API sandbox may satisfy basic functionality if it is genuinely runnable
and easy to test, but it will materially weaken the Design score and the three-minute demo.

