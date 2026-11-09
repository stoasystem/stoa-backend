"""准入: whether a question may be sent, and what its answer is charged.

A question is **admitted** once, when it is first submitted (`admit`): its
eligibility is read once, which gives today's message limit, the plan its
attachments are counted under and the allowance identity stored with the
command; a usage period that has ended (or was never set) refuses it, and so
does a week with nothing left, both before anything is stored. Replays and the
worker read only what the command stored, so an answer already being generated
when the period ends is finished (#239 decision 8).

A question is charged through its **meter** (`meter(command)`), built from the
message command alone. The meter's `model` is what the answer is asked of in
production (`ask_answer.ModelCall.model`): it counts the request's tokens,
reserves them against the week, records that the model is about to be called,
then calls it. What the reply cost is the **usage evidence** (`UsageEvidence`),
which the caller keeps with the answer; with it the meter `observe`s the cost,
then `finalize`s the charge once the answer is stored for good, or `restore`s
the reservation when the answer cannot be used. A command whose cost is not
known is `release`d by the sweep at the reservation's ceiling.

Callers never see the effect id, the beneficiary or the ledger's dispositions:
anything other than success raises `AdmissionError`, carrying the code the
student is sent. The order of those calls is the caller's, unchanged from when
this lived in `_answering` (#218).

"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from stoa.config import settings
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import allowance_repo
from stoa.models.allowance import ProviderUsageEvidence
from stoa.security.attachment_errors import AttachmentDecisionError
from stoa.services import (
    ai_service,
    allowance_service,
    bedrock_token_count_service,
    entitlement_service,
)
from stoa.services.ask_question_errors import AskQuestionErrorCode


class AdmissionError(AttachmentDecisionError):
    """Admission or the allowance refused the answer, or could not say.

    `code` is `USAGE_PERIOD_ENDED`, `ALLOWANCE_EXHAUSTED`,
    `PROVIDER_TOKEN_COUNT_UNAVAILABLE` or `ALLOWANCE_UNAVAILABLE`; it is
    rendered like every other question code.
    """


def _unavailable(detail: str | None = None) -> AdmissionError:
    return AdmissionError(AskQuestionErrorCode.ALLOWANCE_UNAVAILABLE, internal_detail=detail)


def _is_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _observed_at(command: Mapping[str, object]) -> datetime:
    created_at = str(command.get("created_at") or "")
    try:
        observed_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        raise _unavailable() from None
    if observed_at.tzinfo is None:
        raise _unavailable()
    return observed_at


# ── Admission, when a question is first submitted ─────────────────────────────


@dataclass(frozen=True, slots=True)
class Admitted:
    """What a first submission may go ahead with, from its one eligibility read."""

    daily_limit: int
    """Today's message limit, enforced where the command is claimed."""
    attachment_plan: str
    """The plan the message's attachments are counted under."""
    identity: dict[str, object]
    """The allowance fields the command is stored with (`ALLOWANCE_IDENTITY_FIELDS`)."""


def admit(student_id: str, command_draft: Mapping[str, object]) -> Admitted:
    """Admit a question being submitted for the first time.

    `command_draft` is the command about to be claimed. Raises `AdmissionError`,
    always before today's message is counted or anything is stored:
    `USAGE_PERIOD_ENDED` when the student's effective usage period is not
    active (`newUsageAllowed`, judged in the same eligibility read);
    `ALLOWANCE_EXHAUSTED` when the week has nothing left in either dimension;
    `ALLOWANCE_UNAVAILABLE` when the eligibility cannot be read.
    """
    entitlement = _read_entitlement(student_id)
    if entitlement.get("newUsageAllowed") is not True:
        raise AdmissionError(AskQuestionErrorCode.USAGE_PERIOD_ENDED)
    identity = allowance_identity(command_draft, entitlement)
    if allowance_service.week_exhausted(
        beneficiary_id=student_id,
        plan_id=str(identity["allowance_plan_id"]),
        allowance_version=_whole(identity["allowance_version"]),
        observed_at=_observed_at(command_draft),
    ):
        raise AdmissionError(AskQuestionErrorCode.ALLOWANCE_EXHAUSTED)
    limits = entitlement.get("limits")
    daily_limit = (
        stored_int(limits.get("dailyChatMessageLimit"))
        if isinstance(limits, Mapping)
        else None
    )
    return Admitted(
        daily_limit=(
            settings.daily_chat_message_limit if daily_limit is None else daily_limit
        ),
        attachment_plan=str(entitlement.get("effectivePlan") or "free_trial"),
        identity=identity,
    )


def identity_of_unstamped(command: Mapping[str, object]) -> dict[str, object]:
    """The allowance identity of a command claimed without one stored on it.

    Commands claimed before 2026-07-24 (476-18) were stored without it, and
    one left `message_committed` or failed then is still resumable. Reads the
    student's eligibility as it is now; every newer command carries its own.
    """
    student_id = str(command.get("student_id") or command.get("owner_id") or "")
    if not student_id:
        raise _unavailable()
    return allowance_identity(command, _read_entitlement(student_id))


def _read_entitlement(student_id: str) -> Mapping[str, object]:
    """The student's eligibility: the one place a question reads it."""
    entitlement = entitlement_service.resolve_student_entitlement(
        student_id, settings=settings
    )
    if not isinstance(entitlement, Mapping):
        raise _unavailable()
    return entitlement


def _whole(value: object) -> int:
    whole = stored_int(value)
    if whole is None:
        raise _unavailable()
    return whole


# ── The allowance identity a command is charged under ─────────────────────────


def allowance_identity(
    command: Mapping[str, object],
    entitlement: Mapping[str, object],
) -> dict[str, object]:
    """The allowance fields a new command is stored with, from its entitlement.

    One effect per command: the id digests the command, the student, the plan,
    its grant and allowance version, and the Zurich week the command was made in.
    """
    command_id = str(command.get("command_id") or "")
    assistant_message_id = str(command.get("assistant_message_id") or "")
    student_id = str(command.get("student_id") or command.get("owner_id") or "")
    if not command_id or not assistant_message_id or not student_id:
        raise _unavailable()
    observed_at = _observed_at(command)
    plan_id = str(
        entitlement.get("effectivePlan")
        or entitlement.get("effective_plan")
        or "free_trial"
    )
    # The entitlement and the command both come off the table, which returns
    # every stored number as Decimal, and the identity payload below is JSON.
    raw_version = stored_int(
        entitlement.get("allowanceVersion")
        or entitlement.get("allowance_version")
        or entitlement.get("planVersion")
        or 1
    )
    if raw_version is None or raw_version < 1:
        raise _unavailable()
    grant_id = str(
        entitlement.get("grantId")
        or entitlement.get("grant_id")
        or entitlement.get("source")
        or "student-local"
    )
    week_identity = allowance_service.week_identity(observed_at)
    payload = json.dumps(
        {
            "command_id": command_id,
            "assistant_message_id": assistant_message_id,
            "student_id": student_id,
            "plan_id": plan_id,
            "grant_id": grant_id,
            "allowance_version": raw_version,
            "week": week_identity,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    effect_id = hashlib.sha256(
        b"stoa.conversation.allowance-effect.v1\x00" + payload
    ).hexdigest()
    return {
        "allowance_effect_id": effect_id,
        "allowance_plan_id": plan_id,
        "allowance_grant_id": grant_id,
        "allowance_version": raw_version,
        "allowance_week_identity": week_identity,
    }


ALLOWANCE_IDENTITY_FIELDS = (
    "allowance_effect_id",
    "allowance_plan_id",
    "allowance_grant_id",
    "allowance_version",
    "allowance_week_identity",
)


# ── Usage evidence ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class UsageEvidence:
    """What one paid reply cost, as kept beside the answer.

    Stored as `to_json()` on the command (`provider_result_json.allowance`,
    `result_json._allowance`) and on the assistant's message row; the stored
    shape is the one written before this type existed.
    """

    effect_id: str
    evidence_id: str
    request_id_digest: str
    model_id_digest: str
    input_tokens: int
    output_tokens: int

    @classmethod
    def from_provider(
        cls,
        provider_result: ai_service.AIProviderResult[dict[str, object]],
        *,
        effect_id: str,
    ) -> UsageEvidence:
        """The evidence of an answer the allowance was charged for."""
        if provider_result.invocation_class is not ai_service.AIInvocationClass.USER_ALLOWANCE:
            raise _unavailable()
        return cls._from_usage(provider_result.usage, effect_id=effect_id)

    @classmethod
    def from_failure(cls, failure: BaseException, *, effect_id: str) -> UsageEvidence | None:
        """The evidence of a paid reply that could not be used, if it was paid for."""
        usage = getattr(failure, "usage", None)
        if not isinstance(failure, ai_service.AIInvocationFailure) or usage is None:
            return None
        return cls._from_usage(usage, effect_id=effect_id)

    @classmethod
    def _from_usage(cls, usage: ProviderUsageEvidence, *, effect_id: str) -> UsageEvidence:
        evidence = cls.from_json(
            {
                "allowance_effect_id": effect_id,
                "provider_usage_evidence_id": usage.evidence_id,
                "allowance_finalization_status": _FINALIZATION_STATUS,
                "provider_request_id_digest": usage.provider_request_id_digest,
                "provider_model_id_digest": usage.model_id_digest,
                "provider_input_tokens": usage.input_tokens,
                "provider_output_tokens": usage.output_tokens,
            }
        )
        if evidence is None:
            raise _unavailable()
        return evidence

    @classmethod
    def from_json(cls, value: object) -> UsageEvidence | None:
        """Read back what `to_json` stored; None for anything else."""
        if not isinstance(value, Mapping) or not _STORED_FIELDS.issubset(value):
            return None
        if not all(
            _is_digest(value[field])
            for field in (
                "allowance_effect_id",
                "provider_request_id_digest",
                "provider_model_id_digest",
            )
        ):
            return None
        # The table returns stored counts as Decimal.
        input_tokens = stored_int(value["provider_input_tokens"])
        output_tokens = stored_int(value["provider_output_tokens"])
        evidence_id = value["provider_usage_evidence_id"]
        if (
            not isinstance(evidence_id, str)
            or not evidence_id
            or value["allowance_finalization_status"] != _FINALIZATION_STATUS
            or input_tokens is None
            or input_tokens < 0
            or output_tokens is None
            or output_tokens < 0
        ):
            return None
        return cls(
            effect_id=str(value["allowance_effect_id"]),
            evidence_id=evidence_id,
            request_id_digest=str(value["provider_request_id_digest"]),
            model_id_digest=str(value["provider_model_id_digest"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def to_json(self) -> dict[str, object]:
        return {
            "allowance_effect_id": self.effect_id,
            "provider_usage_evidence_id": self.evidence_id,
            "allowance_finalization_status": _FINALIZATION_STATUS,
            "provider_request_id_digest": self.request_id_digest,
            "provider_model_id_digest": self.model_id_digest,
            "provider_input_tokens": self.input_tokens,
            "provider_output_tokens": self.output_tokens,
        }


_FINALIZATION_STATUS = "durable_result_boundary"
_STORED_FIELDS = frozenset(
    {
        "allowance_effect_id",
        "provider_usage_evidence_id",
        "allowance_finalization_status",
        "provider_request_id_digest",
        "provider_model_id_digest",
        "provider_input_tokens",
        "provider_output_tokens",
    }
)


# ── The meter ─────────────────────────────────────────────────────────────────


def meter(command: Mapping[str, object]) -> Meter:
    """The meter one message command's answer is charged through."""
    return Meter(command)


class Meter:
    """Charge one command's answer to its student's weekly allowance."""

    def __init__(self, command: Mapping[str, object]) -> None:
        self._command = dict(command)

    def model(self, on_invocation: Callable[[], bool] | None = None) -> MeteredModel:
        """What the answer is asked of: the Bedrock runtime behind the allowance.

        `on_invocation` records that the model is about to be called; when it
        returns False the call is not made. Raises `AdmissionError` when the
        command's allowance identity does not hold together.
        """
        return MeteredModel(self._command, on_invocation=on_invocation)

    def observe(self, evidence: UsageEvidence) -> None:
        """Record what the reply cost, before the answer is stored."""
        beneficiary = self._beneficiary(evidence)
        observed = allowance_service.record_provider_usage(
            beneficiary_id=beneficiary,
            effect_id=evidence.effect_id,
            provider_request_id=evidence.request_id_digest,
            model_id=evidence.model_id_digest,
            input_tokens=evidence.input_tokens,
            output_tokens=evidence.output_tokens,
        )
        if (
            observed.disposition
            not in {
                allowance_repo.ProviderUsageDisposition.RECORDED,
                allowance_repo.ProviderUsageDisposition.REPLAYED,
            }
            or observed.evidence is None
        ):
            raise _unavailable(f"observe:{observed.disposition.value}")

    def finalize(self, evidence: UsageEvidence) -> None:
        """Charge what was observed, once the answer is stored for good."""
        beneficiary = self._beneficiary(evidence)
        finalized = allowance_service.finalize_token_allowance(
            beneficiary_id=beneficiary,
            effect_id=evidence.effect_id,
            technical_validation_passed=True,
            safety_check_passed=True,
            durable_result_stored=True,
            stable_replay_readable=True,
        )
        if (
            finalized.disposition
            not in {
                allowance_repo.FinalizationDisposition.FINALIZED,
                allowance_repo.FinalizationDisposition.REPLAYED,
            }
            or finalized.finalization is None
        ):
            raise _unavailable(f"finalize:{finalized.disposition.value}")

    def restore(self, evidence: UsageEvidence) -> None:
        """Give the student back a reply that was paid for but cannot be used."""
        beneficiary = self._beneficiary(evidence)
        restored = allowance_service.restore_user_allowance(
            beneficiary_id=beneficiary,
            effect_id=evidence.effect_id,
            technical_validation_passed=False,
            safety_check_passed=True,
            durable_result_stored=False,
            stable_replay_readable=False,
        )
        if (
            restored.disposition
            not in {
                allowance_repo.FinalizationDisposition.RESTORED,
                allowance_repo.FinalizationDisposition.REPLAYED,
            }
            or restored.finalization is None
        ):
            raise _unavailable(f"restore:{restored.disposition.value}")

    def release(self) -> bool:
        """Release what the command left reserved, its cost at the ceiling.

        For the sweep, when no evidence of the cost was kept. Returns whether
        this call released it; False when it had nothing reserved, or another
        run already settled it.
        """
        effect_id = self._command.get("allowance_effect_id")
        if not isinstance(effect_id, str) or not effect_id:
            return False
        released = allowance_service.release_unknown_cost_allowance(
            beneficiary_id=self._student_id(),
            effect_id=effect_id,
        )
        if released.disposition in {
            allowance_repo.ReleaseDisposition.RETRYABLE,
            allowance_repo.ReleaseDisposition.INVALID_STATE,
        }:
            raise _unavailable(f"release:{released.disposition.value}")
        return released.disposition is allowance_repo.ReleaseDisposition.RELEASED

    def _student_id(self) -> str:
        student_id = self._command.get("student_id") or self._command.get("owner_id")
        if not isinstance(student_id, str) or not student_id:
            raise _unavailable()
        return student_id

    def _beneficiary(self, evidence: UsageEvidence) -> str:
        """The student charged, once `evidence` is known to be this command's."""
        command_effect_id = self._command.get("allowance_effect_id")
        if command_effect_id is not None and command_effect_id != evidence.effect_id:
            raise _unavailable()
        return self._student_id()


def _coordinates(command: Mapping[str, object]) -> tuple[str, str, int, int]:
    """The effect, plan, allowance version and fence generation a command is charged under."""
    effect_id = command.get("allowance_effect_id")
    plan_id = command.get("allowance_plan_id")
    grant_id = command.get("allowance_grant_id")
    week_identity = command.get("allowance_week_identity")
    # The table returns both numbers as Decimal, and everything downstream of
    # here takes whole `int` only.
    allowance_version = stored_int(command.get("allowance_version"))
    generation = stored_int(command.get("account_fence_generation"))
    if (
        not _is_digest(effect_id)
        or not isinstance(plan_id, str)
        or not plan_id
        or not isinstance(grant_id, str)
        or not grant_id
        or not isinstance(week_identity, str)
        or not week_identity
        or allowance_version is None
        or allowance_version < 1
        or generation is None
        or generation < 1
    ):
        raise _unavailable()
    expected = allowance_identity(
        command,
        {
            "effectivePlan": plan_id,
            "grantId": grant_id,
            "allowanceVersion": allowance_version,
        },
    )
    if (
        expected["allowance_effect_id"] != effect_id
        or expected["allowance_week_identity"] != week_identity
    ):
        raise _unavailable()
    return str(effect_id), plan_id, allowance_version, generation


class MeteredModel:
    """Count and reserve the command's effect before InvokeModel."""

    def __init__(
        self,
        command: Mapping[str, object],
        *,
        on_invocation: Callable[[], bool] | None = None,
    ) -> None:
        self._deadline_monotonic: float | None = None
        self._clock: Callable[[], float] = time.monotonic
        (
            self.effect_id,
            self.plan_id,
            self.allowance_version,
            self.account_fence_generation,
        ) = _coordinates(command)
        self._command = dict(command)
        self._observed_at = _observed_at(command)
        self._runtime_client: object | None = None
        self._invocation_method = "invoke_model"
        # Records that the model is about to be called; False means the call
        # may not be made.
        self._on_invocation = on_invocation

    def mark_invocation(self) -> None:
        """Record the call before it is made; refuse one that was not recorded.

        Nothing has been paid for at this point, so the failures raised here
        leave the command free to be generated again.
        """
        if self._on_invocation is None:
            return
        try:
            recorded = self._on_invocation()
        except Exception:
            raise ai_service.AIInvocationFailure("invocation_not_recorded") from None
        if not recorded:
            raise ai_service.AIInvocationFailure("lease_lost")

    def bind_deadline(self, deadline_monotonic: float, clock: Callable[[], float]) -> None:
        """Take the answer's deadline from `ai_service.invoke_answer`, its one source."""
        self._deadline_monotonic = deadline_monotonic
        self._clock = clock

    def invoke_model(self, **kwargs: object) -> object:
        model_id = kwargs.get("modelId")
        request_body = kwargs.get("body")
        if not isinstance(model_id, str) or not isinstance(request_body, str):
            raise AdmissionError(AskQuestionErrorCode.PROVIDER_TOKEN_COUNT_UNAVAILABLE)
        remaining = (
            None
            if self._deadline_monotonic is None
            else self._deadline_monotonic - self._clock()
        )
        runtime_client = self._runtime_client or ai_service.boto3.client(
            "bedrock-runtime",
            region_name=ai_service.settings.aws_region,
            config=ai_service.bedrock_runtime_config(remaining),
        )
        self._runtime_client = runtime_client
        try:
            foundation_model_id = (
                bedrock_token_count_service.foundation_model_id_for_profile(
                    model_id
                )
            )
            inference_profile_id: str | None = model_id
        except bedrock_token_count_service.ProviderTokenCountUnavailable:
            foundation_model_id = model_id
            inference_profile_id = None
        try:
            input_tokens = bedrock_token_count_service.count_input_tokens(
                request_body,
                model_id=foundation_model_id,
                inference_profile_id=inference_profile_id,
                region=ai_service.settings.aws_region,
                runtime_client=runtime_client,
            )
            parsed_body = json.loads(request_body)
            max_output_tokens = parsed_body.get("max_tokens")
            if type(max_output_tokens) is not int or max_output_tokens < 1:
                raise bedrock_token_count_service.ProviderTokenCountUnavailable()
        except (
            bedrock_token_count_service.ProviderTokenCountUnavailable,
            json.JSONDecodeError,
        ):
            raise AdmissionError(
                AskQuestionErrorCode.PROVIDER_TOKEN_COUNT_UNAVAILABLE
            ) from None

        reservation = allowance_service.reserve_token_allowance(
            beneficiary_id=str(self._command["student_id"]),
            effect_id=self.effect_id,
            plan_id=self.plan_id,
            allowance_version=self.allowance_version,
            input_tokens=input_tokens,
            max_output_tokens=max_output_tokens,
            observed_at=self._observed_at,
            account_fence_generation=self.account_fence_generation,
        )
        if reservation.disposition is allowance_repo.ReservationDisposition.LIMIT_EXCEEDED:
            raise AdmissionError(AskQuestionErrorCode.ALLOWANCE_EXHAUSTED)
        if reservation.disposition not in {
            allowance_repo.ReservationDisposition.ADMITTED,
            allowance_repo.ReservationDisposition.REPLAYED,
        }:
            raise _unavailable(f"reserve:{reservation.disposition.value}")

        # Counting and reserving can take the time up. Starting a generation
        # now would only be cut off by the Lambda; fail recoverably instead.
        # The reservation is kept on purpose: the ledger restores only after
        # provider usage, and the student's retry of this message reuses it.
        if (
            self._deadline_monotonic is not None
            and self._clock() >= self._deadline_monotonic
        ):
            raise ai_service.AIInvocationFailure("deadline_exceeded")

        invoke = getattr(runtime_client, self._invocation_method, None)
        if not callable(invoke):
            raise RuntimeError("Bedrock invocation dependency unavailable")
        self.mark_invocation()
        return invoke(**kwargs)

    def invoke_model_with_response_stream(self, **kwargs: object) -> object:
        """Admit the same way, then stream. Admission does not depend on how
        the answer is delivered."""
        self._invocation_method = "invoke_model_with_response_stream"
        try:
            return self.invoke_model(**kwargs)
        finally:
            self._invocation_method = "invoke_model"
