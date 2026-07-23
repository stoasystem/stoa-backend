"""Bounded preview/apply job for exact question-submission coordinates."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from typing import Any, Sequence

from stoa.db.repositories import question_submission_repo


DEFAULT_LIMIT = 25
MAX_LIMIT = 100
MAX_STUDENT_ID_LENGTH = 128


class _RedactedArgumentParser(argparse.ArgumentParser):
    """Emit one coordinate-free CLI diagnostic for every parse failure."""

    def error(self, _message: str) -> None:
        self.exit(2, f"{self.prog}: error: question reconciliation input is invalid\n")


@dataclass(frozen=True, slots=True)
class QuestionReconciliationCoordinate:
    """One explicit opaque command coordinate supplied by an operator."""

    student_id: str
    command_digest: str


@dataclass(frozen=True, slots=True)
class QuestionReconciliationJobResult:
    mode: str
    inspected: int
    mutated: int
    results: tuple[dict[str, object], ...]

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


def reconcile_question_submissions(
    coordinates: Sequence[QuestionReconciliationCoordinate],
    *,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
    repository: Any = question_submission_repo,
    table: object | None = None,
    now: datetime | None = None,
) -> QuestionReconciliationJobResult:
    """Inspect only the caller-supplied bounded coordinates; preview is the default."""
    bounded_limit = _validated_limit(limit)
    if len(coordinates) > MAX_LIMIT:
        raise ValueError("question reconciliation input is invalid")
    validated = tuple(_validated_coordinate(value) for value in coordinates)
    selected = validated[:bounded_limit]
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    results: list[dict[str, object]] = []
    mutated = 0
    for coordinate in selected:
        preview = repository.preview_question_submission_reconciliation(
            student_id=coordinate.student_id,
            idempotency_key=coordinate.command_digest,
            table=table,
        )
        outcome = preview
        if apply:
            outcome = repository.apply_question_submission_reconciliation(
                preview,
                student_id=coordinate.student_id,
                idempotency_key=coordinate.command_digest,
                applied_at=timestamp,
                table=table,
            )
        mutated += outcome.mutation_count
        results.append(
            {
                "disposition": outcome.disposition.value,
                "commandId": outcome.command_id,
                "questionId": outcome.question_id,
                "observedCommandVersion": outcome.observed_command_version,
                "observedQuestionVersion": outcome.observed_question_version,
                "observedDigest": outcome.observed_digest,
                "proposedAction": outcome.proposed_action,
                "mutationCount": outcome.mutation_count,
            }
        )
    return QuestionReconciliationJobResult(
        mode="apply" if apply else "preview",
        inspected=len(selected),
        mutated=mutated,
        results=tuple(results),
    )


def reconcile_proven_terminal_question(
    *,
    student_id: str,
    command_digest: str,
    repository: Any = question_submission_repo,
    table: object | None = None,
    now: datetime | None = None,
) -> QuestionReconciliationJobResult:
    """Apply one production-proven terminal coordinate without discovery."""
    coordinate = _validated_coordinate(
        QuestionReconciliationCoordinate(
            student_id=student_id,
            command_digest=command_digest,
        )
    )
    return reconcile_question_submissions(
        (coordinate,),
        apply=True,
        limit=1,
        repository=repository,
        table=table,
        now=now,
    )


def _validated_limit(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_LIMIT
    ):
        raise ValueError("question reconciliation input is invalid")
    return value


def _validated_coordinate(value: object) -> QuestionReconciliationCoordinate:
    if not isinstance(value, QuestionReconciliationCoordinate):
        raise ValueError("question reconciliation coordinate is invalid")
    student_id = value.student_id
    if (
        not isinstance(student_id, str)
        or not student_id
        or student_id != student_id.strip()
        or len(student_id) > MAX_STUDENT_ID_LENGTH
    ):
        raise ValueError("question reconciliation coordinate is invalid")
    try:
        command_digest = (
            question_submission_repo.validate_question_submission_command_digest(
                value.command_digest
            )
        )
    except ValueError as exc:
        raise ValueError("question reconciliation coordinate is invalid") from exc
    return QuestionReconciliationCoordinate(
        student_id=student_id,
        command_digest=command_digest,
    )


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, object]:
    """Lambda entrypoint requiring an explicit bounded coordinate list."""
    if event is None or set(event) - {"coordinates", "mode", "limit"}:
        raise ValueError("question reconciliation input is invalid")
    raw_coordinates = event.get("coordinates")
    if (
        not isinstance(raw_coordinates, list)
        or not raw_coordinates
        or len(raw_coordinates) > MAX_LIMIT
    ):
        raise ValueError("question reconciliation input is invalid")
    mode = event.get("mode", "preview")
    if mode not in {"preview", "apply"}:
        raise ValueError("question reconciliation input is invalid")
    limit = _validated_limit(event.get("limit", DEFAULT_LIMIT))
    coordinates: list[QuestionReconciliationCoordinate] = []
    for value in raw_coordinates:
        if not isinstance(value, dict) or set(value) != {"studentId", "commandDigest"}:
            raise ValueError("question reconciliation coordinate is invalid")
        student_id = value.get("studentId")
        command_digest = value.get("commandDigest")
        if not isinstance(student_id, str) or not isinstance(command_digest, str):
            raise ValueError("question reconciliation coordinate is invalid")
        coordinates.append(
            _validated_coordinate(
                QuestionReconciliationCoordinate(
                    student_id=student_id,
                    command_digest=command_digest,
                )
            )
        )
    return reconcile_question_submissions(
        coordinates,
        apply=mode == "apply",
        limit=limit,
    ).public_dict()


def _parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(
        description="Preview or apply one bounded question reconciliation coordinate."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Inspect without writes (default).")
    mode.add_argument("--apply", action="store_true", help="Apply the preview-bound proposal.")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--command-digest", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        coordinate = _validated_coordinate(
            QuestionReconciliationCoordinate(
                student_id=args.student_id,
                command_digest=args.command_digest,
            )
        )
    except ValueError:
        parser.error("question reconciliation input is invalid")
    result = reconcile_question_submissions((coordinate,), apply=args.apply)
    print(json.dumps(result.public_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
