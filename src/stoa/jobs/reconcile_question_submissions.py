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


@dataclass(frozen=True, slots=True)
class QuestionReconciliationJobResult:
    mode: str
    inspected: int
    mutated: int
    results: tuple[dict[str, object], ...]

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


def reconcile_question_submissions(
    coordinates: Sequence[question_submission_repo.QuestionReconciliationCoordinate],
    *,
    apply: bool = False,
    limit: int = DEFAULT_LIMIT,
    repository: Any = question_submission_repo,
    table: object | None = None,
    now: datetime | None = None,
) -> QuestionReconciliationJobResult:
    """Inspect only the caller-supplied bounded coordinates; preview is the default."""
    try:
        bounded_limit = min(max(int(limit), 1), MAX_LIMIT)
    except (TypeError, ValueError):
        bounded_limit = DEFAULT_LIMIT
    selected = tuple(coordinates[:bounded_limit])
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    results: list[dict[str, object]] = []
    mutated = 0
    for coordinate in selected:
        preview = repository.preview_question_submission_reconciliation(
            student_id=coordinate.student_id,
            idempotency_key=coordinate.idempotency_key,
            question_id=coordinate.question_id,
            quota_period=coordinate.quota_period,
            table=table,
        )
        outcome = preview
        if apply:
            outcome = repository.apply_question_submission_reconciliation(
                preview,
                student_id=coordinate.student_id,
                idempotency_key=coordinate.idempotency_key,
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


def handler(event: dict[str, Any] | None, _context: Any) -> dict[str, object]:
    """Lambda entrypoint requiring an explicit bounded coordinate list."""
    event = event or {}
    raw_coordinates = event.get("coordinates")
    if not isinstance(raw_coordinates, list):
        raw_coordinates = []
    coordinates: list[question_submission_repo.QuestionReconciliationCoordinate] = []
    for value in raw_coordinates[:MAX_LIMIT]:
        if not isinstance(value, dict):
            continue
        student_id = value.get("studentId")
        idempotency_key = value.get("idempotencyKey")
        if not isinstance(student_id, str) or not student_id:
            continue
        if not isinstance(idempotency_key, str) or not idempotency_key:
            continue
        coordinates.append(
            question_submission_repo.QuestionReconciliationCoordinate(
                student_id=student_id,
                idempotency_key=idempotency_key,
                question_id=(
                    value.get("questionId")
                    if isinstance(value.get("questionId"), str)
                    else None
                ),
                quota_period=(
                    value.get("quotaPeriod")
                    if isinstance(value.get("quotaPeriod"), str)
                    else None
                ),
            )
        )
    return reconcile_question_submissions(
        coordinates,
        apply=event.get("mode") == "apply",
        limit=event.get("limit", DEFAULT_LIMIT),
    ).public_dict()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or apply one bounded question reconciliation coordinate."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="Inspect without writes (default).")
    mode.add_argument("--apply", action="store_true", help="Apply the preview-bound proposal.")
    parser.add_argument("--student-id", required=True)
    parser.add_argument("--idempotency-key", required=True)
    parser.add_argument("--question-id")
    parser.add_argument("--quota-period")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    coordinate = question_submission_repo.QuestionReconciliationCoordinate(
        student_id=args.student_id,
        idempotency_key=args.idempotency_key,
        question_id=args.question_id,
        quota_period=args.quota_period,
    )
    result = reconcile_question_submissions((coordinate,), apply=args.apply)
    print(json.dumps(result.public_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
