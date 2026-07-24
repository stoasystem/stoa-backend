"""Bounded, digest-bound preview/apply migration for canonical billing plan IDs.

The job accepts exact storage coordinates, emits only redacted digests, and
never calls a payment-provider mutation.  Preview is always write-free.  Apply
is restricted to non-production sources and rechecks every source before a
version-conditioned write.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Never, Protocol

from botocore.exceptions import ClientError

from stoa.models.billing import BillingPlanId


SCHEMA_VERSION = "plan_identity_migration_preview.v1"
INPUT_SCHEMA_VERSION = "plan_identity_migration_input.v1"
PLAN_IDENTITY_SCHEMA_VERSION = 1
MAX_COORDINATES = 100
MAX_COORDINATE_LENGTH = 300
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
_ENVIRONMENT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")
_PAID_PLANS = frozenset(
    {
        BillingPlanId.STUDENT,
        BillingPlanId.TEACHER_SUPPORTED,
        BillingPlanId.FAMILY,
    }
)
_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production", "live"})
_RECEIPT_FORBIDDEN_KEYS = frozenset(
    {
        "pk",
        "sk",
        "email",
        "customer",
        "customerid",
        "priceid",
        "subscriptionid",
        "providerid",
        "beneficiaryid",
        "secret",
        "card",
        "cvc",
    }
)


class MigrationBlockedError(RuntimeError):
    """Raised when migration safety evidence is incomplete or stale."""


class PlanMigrationDisposition(StrEnum):
    """Closed preview and apply outcomes."""

    CANONICAL = "canonical"
    EXACT_PROVIDER_MATCH = "exact_provider_match"
    MIGRATION_REVIEW_REQUIRED = "migration_review_required"
    MALFORMED = "malformed"
    CHANGED_EVIDENCE = "changed_evidence"
    APPLIED = "applied"
    REPLAYED = "replayed"


@dataclass(frozen=True, slots=True)
class PlanMigrationCoordinate:
    """One exact source row; coordinates never enter public output."""

    pk: str
    sk: str

    def __post_init__(self) -> None:
        for value in (self.pk, self.sk):
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
                or len(value) > MAX_COORDINATE_LENGTH
            ):
                raise ValueError("plan migration coordinate is invalid")


@dataclass(frozen=True, slots=True)
class PlanMigrationOperatorDisposition:
    """Explicit evidence-bound resolution for one unresolved preview row."""

    coordinate_digest: str
    target_plan: str
    evidence_digest: str

    def __post_init__(self) -> None:
        _required_digest(self.coordinate_digest)
        _required_digest(self.evidence_digest)
        _canonical_plan(self.target_plan)


@dataclass(frozen=True, slots=True)
class PlanMigrationCandidate:
    """One redacted preview candidate plus its private apply coordinate."""

    coordinate_digest: str
    row_digest: str
    evidence_digest: str
    observed_version: int
    source_plan: str
    target_plan: str | None
    disposition: PlanMigrationDisposition
    reason_code: str
    migration_review_required: bool
    _coordinate: PlanMigrationCoordinate

    def public_dict(self) -> dict[str, object]:
        return {
            "coordinateDigest": self.coordinate_digest,
            "rowDigest": self.row_digest,
            "evidenceDigest": self.evidence_digest,
            "observedVersion": self.observed_version,
            "sourcePlan": self.source_plan,
            "targetPlan": self.target_plan,
            "disposition": self.disposition.value,
            "reasonCode": self.reason_code,
            "migrationReviewRequired": self.migration_review_required,
        }

    def unresolved_dict(self) -> dict[str, object]:
        return {
            "coordinateDigest": self.coordinate_digest,
            "rowDigest": self.row_digest,
            "evidenceDigest": self.evidence_digest,
            "sourcePlan": self.source_plan,
            "disposition": self.disposition.value,
            "reasonCode": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class PlanMigrationPreview:
    """Whole-inventory preview bound to configuration, source, and row evidence."""

    environment: str
    source_sha: str
    configuration_digest: str
    preview_digest: str
    candidates: tuple[PlanMigrationCandidate, ...]
    _price_plan_by_id: tuple[tuple[str, str], ...]

    @property
    def mutation_count(self) -> int:
        return 0

    def public_receipt(self) -> dict[str, object]:
        counts = Counter(candidate.disposition.value for candidate in self.candidates)
        unresolved = [
            candidate.unresolved_dict()
            for candidate in self.candidates
            if candidate.migration_review_required
        ]
        return {
            "schemaVersion": SCHEMA_VERSION,
            "status": "review_required" if unresolved else "ready",
            "environment": self.environment,
            "sourceSha": self.source_sha,
            "configurationDigest": self.configuration_digest,
            "previewDigest": self.preview_digest,
            "inspected": len(self.candidates),
            "mutationCount": 0,
            "applyBlocked": bool(unresolved),
            "classificationCounts": {
                disposition.value: counts.get(disposition.value, 0)
                for disposition in (
                    PlanMigrationDisposition.CANONICAL,
                    PlanMigrationDisposition.EXACT_PROVIDER_MATCH,
                    PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
                    PlanMigrationDisposition.MALFORMED,
                )
            },
            "unresolved": unresolved,
        }


@dataclass(frozen=True, slots=True)
class PlanMigrationApplyResult:
    """Conditional apply result; each result remains coordinate-free."""

    preview_digest: str
    mutation_count: int
    results: tuple[PlanMigrationCandidate, ...]

    def public_dict(self) -> dict[str, object]:
        return {
            "previewDigest": self.preview_digest,
            "mutationCount": self.mutation_count,
            "results": [candidate.public_dict() for candidate in self.results],
        }


class PlanMigrationRepository(Protocol):
    """Least-capability persistence boundary used by preview and apply."""

    def read_source(self, coordinate: PlanMigrationCoordinate) -> Mapping[str, object] | None: ...

    def conditional_apply(
        self,
        *,
        coordinate: PlanMigrationCoordinate,
        expected_source_digest: str,
        expected_version: int,
        source_plan: str,
        target_plan: str,
        evidence_digest: str,
        applied_at: str,
    ) -> str: ...


class DynamoPlanMigrationRepository:
    """Strong-read DynamoDB adapter with exact version/source-plan conditions."""

    def __init__(self, table: object) -> None:
        self._table = table

    def read_source(self, coordinate: PlanMigrationCoordinate) -> Mapping[str, object] | None:
        get_item = getattr(self._table, "get_item", None)
        if not callable(get_item):
            raise MigrationBlockedError("migration repository is unavailable")
        response = get_item(
            Key={"PK": coordinate.pk, "SK": coordinate.sk},
            ConsistentRead=True,
        )
        if not isinstance(response, Mapping):
            raise MigrationBlockedError("migration repository returned malformed evidence")
        item = response.get("Item")
        if item is None:
            return None
        if not isinstance(item, Mapping):
            raise MigrationBlockedError("migration repository returned malformed evidence")
        return dict(item)

    def conditional_apply(
        self,
        *,
        coordinate: PlanMigrationCoordinate,
        expected_source_digest: str,
        expected_version: int,
        source_plan: str,
        target_plan: str,
        evidence_digest: str,
        applied_at: str,
    ) -> str:
        current = self.read_source(coordinate)
        if current is None:
            return "changed"
        if (
            current.get("plan_identity_schema_version") == PLAN_IDENTITY_SCHEMA_VERSION
            and current.get("migration_evidence_digest") == evidence_digest
            and current.get("subscription_tier") == target_plan
        ):
            return "replayed"
        if _source_digest(current) != expected_source_digest:
            return "changed"
        history = _migration_history(current, applied_at=applied_at)
        update_item = getattr(self._table, "update_item", None)
        if not callable(update_item):
            raise MigrationBlockedError("migration repository is unavailable")
        try:
            update_item(
                Key={"PK": coordinate.pk, "SK": coordinate.sk},
                UpdateExpression=(
                    "SET #plan=:target_plan, #schema=:schema, #evidence=:evidence, "
                    "#source_plan=:source_plan, #review=:review, #history=:history, "
                    "#version=:next_version"
                ),
                ConditionExpression=(
                    "#version=:expected_version AND #plan=:expected_source_plan"
                ),
                ExpressionAttributeNames={
                    "#plan": "subscription_tier",
                    "#schema": "plan_identity_schema_version",
                    "#evidence": "migration_evidence_digest",
                    "#source_plan": "migration_source_plan",
                    "#review": "migration_review_required",
                    "#history": "plan_identity_migration_history",
                    "#version": "version",
                },
                ExpressionAttributeValues={
                    ":target_plan": target_plan,
                    ":schema": PLAN_IDENTITY_SCHEMA_VERSION,
                    ":evidence": evidence_digest,
                    ":source_plan": source_plan,
                    ":review": False,
                    ":history": history,
                    ":next_version": expected_version + 1,
                    ":expected_version": expected_version,
                    ":expected_source_plan": source_plan,
                },
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return "changed"
            raise
        return "applied"


class LocalInventoryRepository:
    """Read-only/local-fixture adapter used to create non-production evidence."""

    def __init__(self, sources: Mapping[tuple[str, str], Mapping[str, object]]) -> None:
        self._sources = {coordinate: dict(source) for coordinate, source in sources.items()}

    def read_source(self, coordinate: PlanMigrationCoordinate) -> Mapping[str, object] | None:
        source = self._sources.get((coordinate.pk, coordinate.sk))
        return dict(source) if source is not None else None

    def conditional_apply(
        self,
        *,
        coordinate: PlanMigrationCoordinate,
        expected_source_digest: str,
        expected_version: int,
        source_plan: str,
        target_plan: str,
        evidence_digest: str,
        applied_at: str,
    ) -> str:
        source = self._sources.get((coordinate.pk, coordinate.sk))
        if source is None or _source_digest(source) != expected_source_digest:
            return "changed"
        if (
            source.get("plan_identity_schema_version") == PLAN_IDENTITY_SCHEMA_VERSION
            and source.get("migration_evidence_digest") == evidence_digest
            and source.get("subscription_tier") == target_plan
        ):
            return "replayed"
        if (
            source.get("version") != expected_version
            or source.get("subscription_tier") != source_plan
        ):
            return "changed"
        source["plan_identity_migration_history"] = _migration_history(
            source, applied_at=applied_at
        )
        source["subscription_tier"] = target_plan
        source["plan_identity_schema_version"] = PLAN_IDENTITY_SCHEMA_VERSION
        source["migration_evidence_digest"] = evidence_digest
        source["migration_source_plan"] = source_plan
        source["migration_review_required"] = False
        source["version"] = expected_version + 1
        return "applied"


def preview_plan_identity_migration(
    coordinates: Sequence[PlanMigrationCoordinate],
    *,
    environment: str,
    price_plan_by_id: Mapping[str, str],
    repository: PlanMigrationRepository,
    source_sha: str,
) -> PlanMigrationPreview:
    """Strong-read a bounded exact inventory and produce a zero-write preview."""
    validated_environment = _non_production_environment(environment)
    validated_source_sha = _source_sha(source_sha)
    validated_prices = _validated_price_plan_map(price_plan_by_id)
    validated_coordinates = _validated_coordinates(coordinates)
    candidates: list[PlanMigrationCandidate] = []
    for coordinate in validated_coordinates:
        source = repository.read_source(coordinate)
        candidates.append(_classify_source(coordinate, source, validated_prices))
    configuration_digest = _digest(
        {
            "environment": validated_environment,
            "prices": sorted(
                (_digest_text(price_id), plan.value)
                for price_id, plan in validated_prices.items()
            ),
            "schema": PLAN_IDENTITY_SCHEMA_VERSION,
        }
    )
    price_pairs = tuple(
        sorted((price_id, plan.value) for price_id, plan in validated_prices.items())
    )
    preview_digest = _preview_integrity_digest(
        environment=validated_environment,
        source_sha=validated_source_sha,
        configuration_digest=configuration_digest,
        candidates=tuple(candidates),
    )
    return PlanMigrationPreview(
        environment=validated_environment,
        source_sha=validated_source_sha,
        configuration_digest=configuration_digest,
        preview_digest=preview_digest,
        candidates=tuple(candidates),
        _price_plan_by_id=price_pairs,
    )


def apply_plan_identity_migration(
    preview: PlanMigrationPreview,
    *,
    preview_digest: str,
    operator_dispositions: Mapping[str, PlanMigrationOperatorDisposition],
    repository: PlanMigrationRepository,
    environment: str,
    applied_at: str,
) -> PlanMigrationApplyResult:
    """Apply only the exact unchanged preview, with no provider mutation."""
    validated_environment = _non_production_environment(environment)
    if validated_environment != preview.environment:
        raise MigrationBlockedError("migration environment does not match preview")
    _required_digest(preview_digest)
    if preview_digest != preview.preview_digest:
        raise MigrationBlockedError("migration preview digest does not match")
    expected_integrity = _preview_integrity_digest(
        environment=preview.environment,
        source_sha=preview.source_sha,
        configuration_digest=preview.configuration_digest,
        candidates=preview.candidates,
    )
    if expected_integrity != preview.preview_digest:
        raise MigrationBlockedError("migration preview integrity check failed")
    _validated_applied_at(applied_at)
    dispositions = _validated_operator_dispositions(preview, operator_dispositions)
    price_map = {
        price_id: _canonical_plan(plan) for price_id, plan in preview._price_plan_by_id
    }

    results: list[PlanMigrationCandidate] = []
    pending: list[tuple[PlanMigrationCandidate, str]] = []
    for candidate in preview.candidates:
        target_plan = candidate.target_plan
        if candidate.disposition is PlanMigrationDisposition.MALFORMED:
            raise MigrationBlockedError("malformed or live provider evidence blocks apply")
        if candidate.migration_review_required:
            target_plan = dispositions[candidate.coordinate_digest].target_plan
        if target_plan is None:
            raise MigrationBlockedError("migration target is unresolved")
        current = repository.read_source(candidate._coordinate)
        if current is not None and _is_replayed_source(
            current,
            target_plan=target_plan,
            evidence_digest=candidate.evidence_digest,
        ):
            results.append(
                replace(
                    candidate,
                    target_plan=target_plan,
                    disposition=PlanMigrationDisposition.REPLAYED,
                    reason_code="already_applied",
                    migration_review_required=False,
                )
            )
            continue
        current_candidate = _classify_source(candidate._coordinate, current, price_map)
        if (
            current_candidate.row_digest != candidate.row_digest
            or current_candidate.evidence_digest != candidate.evidence_digest
            or current_candidate.observed_version != candidate.observed_version
        ):
            results.append(
                replace(
                    candidate,
                    target_plan=target_plan,
                    disposition=PlanMigrationDisposition.CHANGED_EVIDENCE,
                    reason_code="source_changed_after_preview",
                )
            )
            continue
        pending.append((candidate, target_plan))

    mutation_count = 0
    for candidate, target_plan in pending:
        outcome = repository.conditional_apply(
            coordinate=candidate._coordinate,
            expected_source_digest=candidate.row_digest,
            expected_version=candidate.observed_version,
            source_plan=candidate.source_plan,
            target_plan=target_plan,
            evidence_digest=candidate.evidence_digest,
            applied_at=applied_at,
        )
        if outcome == "applied":
            disposition = PlanMigrationDisposition.APPLIED
            reason_code = "conditional_write_applied"
            mutation_count += 1
        elif outcome == "replayed":
            disposition = PlanMigrationDisposition.REPLAYED
            reason_code = "already_applied"
        elif outcome == "changed":
            disposition = PlanMigrationDisposition.CHANGED_EVIDENCE
            reason_code = "conditional_source_changed"
        else:
            raise MigrationBlockedError("migration repository returned an invalid outcome")
        results.append(
            replace(
                candidate,
                target_plan=target_plan,
                disposition=disposition,
                reason_code=reason_code,
                migration_review_required=False,
            )
        )
    results.sort(key=lambda candidate: candidate.coordinate_digest)
    return PlanMigrationApplyResult(
        preview_digest=preview.preview_digest,
        mutation_count=mutation_count,
        results=tuple(results),
    )


def verify_preview_receipt(path: str | Path) -> dict[str, object]:
    """Verify the checked receipt schema and redaction boundary."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationBlockedError("migration preview receipt is invalid") from exc
    if not isinstance(document, dict):
        raise MigrationBlockedError("migration preview receipt is invalid")
    required_keys = {
        "schemaVersion",
        "status",
        "environment",
        "sourceSha",
        "configurationDigest",
        "previewDigest",
        "inspected",
        "mutationCount",
        "applyBlocked",
        "classificationCounts",
        "unresolved",
    }
    if set(document) != required_keys or document.get("schemaVersion") != SCHEMA_VERSION:
        raise MigrationBlockedError("migration preview receipt schema is invalid")
    _non_production_environment(document.get("environment"))
    _source_sha(document.get("sourceSha"))
    _required_digest(document.get("configurationDigest"))
    _required_digest(document.get("previewDigest"))
    inspected = document.get("inspected")
    mutation_count = document.get("mutationCount")
    if (
        isinstance(inspected, bool)
        or not isinstance(inspected, int)
        or inspected < 1
        or isinstance(mutation_count, bool)
        or mutation_count != 0
    ):
        raise MigrationBlockedError("migration preview receipt counts are invalid")
    unresolved = document.get("unresolved")
    counts = document.get("classificationCounts")
    if not isinstance(unresolved, list) or not isinstance(counts, dict):
        raise MigrationBlockedError("migration preview receipt classifications are invalid")
    expected_status = "review_required" if unresolved else "ready"
    if (
        document.get("status") != expected_status
        or document.get("applyBlocked") is not bool(unresolved)
    ):
        raise MigrationBlockedError("migration preview receipt gate is invalid")
    _verify_redacted_tree(document)
    return document


def lambda_handler(event: object, _context: object) -> dict[str, object]:
    """Lambda entrypoint; validate the closed request before table access."""
    if not isinstance(event, dict):
        raise ValueError("plan migration input is invalid")
    mode = event.get("mode", "preview")
    preview_keys = {
        "mode",
        "environment",
        "sourceSha",
        "pricePlanById",
        "coordinates",
    }
    apply_keys = preview_keys | {
        "previewDigest",
        "operatorDispositions",
        "appliedAt",
    }
    if mode == "preview":
        if set(event) != preview_keys:
            raise ValueError("plan migration input is invalid")
    elif mode == "apply":
        if set(event) != apply_keys:
            raise ValueError("plan migration input is invalid")
    else:
        raise ValueError("plan migration input is invalid")
    environment = _non_production_environment(event.get("environment"))
    source_sha = _source_sha(event.get("sourceSha"))
    price_map = _event_price_map(event.get("pricePlanById"))
    coordinates = _event_coordinates(event.get("coordinates"))
    dispositions: dict[str, PlanMigrationOperatorDisposition] = {}
    if mode == "apply":
        _required_digest(event.get("previewDigest"))
        _validated_applied_at(event.get("appliedAt"))
        dispositions = _event_operator_dispositions(event.get("operatorDispositions"))

    # Import and acquire the table only after every untrusted field is validated.
    from stoa.db.dynamodb import get_table

    repository = DynamoPlanMigrationRepository(get_table())
    preview = preview_plan_identity_migration(
        coordinates,
        environment=environment,
        price_plan_by_id=price_map,
        repository=repository,
        source_sha=source_sha,
    )
    if mode == "preview":
        return preview.public_receipt()
    result = apply_plan_identity_migration(
        preview,
        preview_digest=event["previewDigest"],
        operator_dispositions=dispositions,
        repository=repository,
        environment=environment,
        applied_at=event["appliedAt"],
    )
    return result.public_dict()


def _classify_source(
    coordinate: PlanMigrationCoordinate,
    source: Mapping[str, object] | None,
    price_plan_by_id: Mapping[str, BillingPlanId],
) -> PlanMigrationCandidate:
    coordinate_digest = _digest(
        {"domain": "plan-migration-coordinate.v1", "pk": coordinate.pk, "sk": coordinate.sk}
    )
    if source is None:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=_digest({"missing": True}),
            evidence_digest=_digest({"missing": True}),
            observed_version=0,
            source_plan="missing",
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="source_row_missing",
        )
    row = dict(source)
    row_digest = _source_digest(row)
    evidence_digest = _evidence_digest(row)
    if row.get("PK") != coordinate.pk or row.get("SK") != coordinate.sk:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=0,
            source_plan=_safe_source_plan(row.get("subscription_tier")),
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="coordinate_mismatch",
        )
    version = row.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=0,
            source_plan=_safe_source_plan(row.get("subscription_tier")),
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="invalid_row_version",
        )
    source_plan = row.get("subscription_tier")
    if not isinstance(source_plan, str) or not source_plan:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan="malformed",
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="invalid_source_plan",
        )
    try:
        canonical = BillingPlanId(source_plan)
    except ValueError:
        canonical = None
    if canonical is not None:
        if (
            canonical is BillingPlanId.FREE_TRIAL
            and not _valid_first_activation(row.get("first_student_activation_at"))
        ):
            return _candidate(
                coordinate=coordinate,
                coordinate_digest=coordinate_digest,
                row_digest=row_digest,
                evidence_digest=evidence_digest,
                observed_version=version,
                source_plan=source_plan,
                disposition=PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
                reason_code="historical_trial_evidence_missing",
            )
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            target_plan=canonical.value,
            disposition=PlanMigrationDisposition.CANONICAL,
            reason_code="canonical_plan_validated",
            migration_review_required=False,
        )
    if source_plan not in {"free", "standard", "premium", "tutor_supported"}:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="unknown_source_plan",
        )
    if source_plan == "free":
        if _valid_first_activation(row.get("first_student_activation_at")):
            return _candidate(
                coordinate=coordinate,
                coordinate_digest=coordinate_digest,
                row_digest=row_digest,
                evidence_digest=evidence_digest,
                observed_version=version,
                source_plan=source_plan,
                target_plan=BillingPlanId.FREE_TRIAL.value,
                disposition=PlanMigrationDisposition.EXACT_PROVIDER_MATCH,
                reason_code="historical_trial_evidence_validated",
                migration_review_required=False,
            )
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
            reason_code="historical_trial_evidence_missing",
        )
    provider_evidence = row.get("provider_evidence")
    if provider_evidence is None:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
            reason_code="provider_evidence_missing",
        )
    if not isinstance(provider_evidence, Mapping):
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="provider_evidence_malformed",
        )
    if set(provider_evidence) != {"price_id", "subscription_id", "livemode"}:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="provider_evidence_malformed",
        )
    if provider_evidence.get("livemode") is not False:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="provider_livemode_forbidden",
        )
    price_id = provider_evidence.get("price_id")
    subscription_id = provider_evidence.get("subscription_id")
    if (
        not isinstance(price_id, str)
        or not price_id
        or not isinstance(subscription_id, str)
        or not subscription_id
    ):
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MALFORMED,
            reason_code="provider_evidence_malformed",
        )
    target_plan = price_plan_by_id.get(price_id)
    if target_plan is None:
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
            reason_code="configured_price_match_missing",
        )
    beneficiaries = _beneficiaries(row.get("plan_beneficiary_ids"))
    if not _beneficiary_scope_matches(target_plan, beneficiaries):
        return _candidate(
            coordinate=coordinate,
            coordinate_digest=coordinate_digest,
            row_digest=row_digest,
            evidence_digest=evidence_digest,
            observed_version=version,
            source_plan=source_plan,
            disposition=PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
            reason_code="explicit_beneficiary_evidence_missing",
        )
    return _candidate(
        coordinate=coordinate,
        coordinate_digest=coordinate_digest,
        row_digest=row_digest,
        evidence_digest=evidence_digest,
        observed_version=version,
        source_plan=source_plan,
        target_plan=target_plan.value,
        disposition=PlanMigrationDisposition.EXACT_PROVIDER_MATCH,
        reason_code="sandbox_price_subscription_beneficiary_match",
        migration_review_required=False,
    )


def _candidate(
    *,
    coordinate: PlanMigrationCoordinate,
    coordinate_digest: str,
    row_digest: str,
    evidence_digest: str,
    observed_version: int,
    source_plan: str,
    disposition: PlanMigrationDisposition,
    reason_code: str,
    target_plan: str | None = None,
    migration_review_required: bool = True,
) -> PlanMigrationCandidate:
    return PlanMigrationCandidate(
        coordinate_digest=coordinate_digest,
        row_digest=row_digest,
        evidence_digest=evidence_digest,
        observed_version=observed_version,
        source_plan=source_plan,
        target_plan=target_plan,
        disposition=disposition,
        reason_code=reason_code,
        migration_review_required=migration_review_required,
        _coordinate=coordinate,
    )


def _validated_coordinates(
    coordinates: Sequence[PlanMigrationCoordinate],
) -> tuple[PlanMigrationCoordinate, ...]:
    if (
        isinstance(coordinates, (str, bytes))
        or not coordinates
        or len(coordinates) > MAX_COORDINATES
    ):
        raise ValueError("plan migration coordinates are invalid")
    validated: list[PlanMigrationCoordinate] = []
    seen: set[tuple[str, str]] = set()
    for coordinate in coordinates:
        if not isinstance(coordinate, PlanMigrationCoordinate):
            raise ValueError("plan migration coordinate is invalid")
        key = (coordinate.pk, coordinate.sk)
        if key in seen:
            raise ValueError("plan migration coordinate is duplicated")
        seen.add(key)
        validated.append(coordinate)
    return tuple(validated)


def _validated_price_plan_map(
    value: Mapping[str, str],
) -> dict[str, BillingPlanId]:
    if not isinstance(value, Mapping):
        raise ValueError("plan migration Price configuration is invalid")
    result: dict[str, BillingPlanId] = {}
    for price_id, raw_plan in value.items():
        if (
            not isinstance(price_id, str)
            or not price_id
            or price_id != price_id.strip()
        ):
            raise ValueError("plan migration Price configuration is invalid")
        plan = _canonical_plan(raw_plan)
        if plan not in _PAID_PLANS or price_id in result:
            raise ValueError("plan migration Price configuration is invalid")
        result[price_id] = plan
    if set(result.values()) != _PAID_PLANS or len(result) != len(_PAID_PLANS):
        raise ValueError("plan migration Price configuration is incomplete")
    return result


def _validated_operator_dispositions(
    preview: PlanMigrationPreview,
    value: Mapping[str, PlanMigrationOperatorDisposition],
) -> dict[str, PlanMigrationOperatorDisposition]:
    if not isinstance(value, Mapping):
        raise MigrationBlockedError("migration operator dispositions are invalid")
    expected = {
        candidate.coordinate_digest: candidate
        for candidate in preview.candidates
        if candidate.migration_review_required
        and candidate.disposition is PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED
    }
    malformed = [
        candidate
        for candidate in preview.candidates
        if candidate.disposition is PlanMigrationDisposition.MALFORMED
    ]
    if malformed:
        raise MigrationBlockedError("malformed or live provider evidence blocks apply")
    if set(value) != set(expected):
        raise MigrationBlockedError("every review row requires an operator disposition")
    result: dict[str, PlanMigrationOperatorDisposition] = {}
    for coordinate_digest, disposition in value.items():
        if (
            not isinstance(disposition, PlanMigrationOperatorDisposition)
            or disposition.coordinate_digest != coordinate_digest
            or disposition.evidence_digest != expected[coordinate_digest].evidence_digest
        ):
            raise MigrationBlockedError("operator disposition evidence does not match")
        result[coordinate_digest] = disposition
    return result


def _preview_integrity_digest(
    *,
    environment: str,
    source_sha: str,
    configuration_digest: str,
    candidates: tuple[PlanMigrationCandidate, ...],
) -> str:
    return _digest(
        {
            "domain": "plan-identity-migration-preview.v1",
            "environment": environment,
            "sourceSha": source_sha,
            "configurationDigest": configuration_digest,
            "candidates": [candidate.public_dict() for candidate in candidates],
        }
    )


def _source_digest(source: Mapping[str, object]) -> str:
    return _digest({"domain": "plan-migration-source.v1", "row": source})


def _evidence_digest(source: Mapping[str, object]) -> str:
    return _digest(
        {
            "domain": "plan-migration-evidence.v1",
            "sourcePlan": source.get("subscription_tier"),
            "providerEvidence": source.get("provider_evidence"),
            "beneficiaryEvidence": source.get("plan_beneficiary_ids"),
            "firstActivationEvidence": source.get("first_student_activation_at"),
        }
    )


def _migration_history(source: Mapping[str, object], *, applied_at: str) -> list[object]:
    prior_history = source.get("plan_identity_migration_history")
    history = list(prior_history) if isinstance(prior_history, list) else []
    history.append(
        {
            "schema_version": PLAN_IDENTITY_SCHEMA_VERSION,
            "applied_at": applied_at,
            "prior_subscription_tier": source.get("subscription_tier"),
            "prior_plan_identity_schema_version": source.get(
                "plan_identity_schema_version"
            ),
            "prior_migration_evidence_digest": source.get(
                "migration_evidence_digest"
            ),
            "prior_migration_source_plan": source.get("migration_source_plan"),
            "prior_migration_review_required": source.get(
                "migration_review_required"
            ),
            "prior_first_student_activation_at": source.get(
                "first_student_activation_at"
            ),
            "prior_provider_evidence_digest": _evidence_digest(source),
        }
    )
    return history


def _is_replayed_source(
    source: Mapping[str, object],
    *,
    target_plan: str,
    evidence_digest: str,
) -> bool:
    return (
        source.get("plan_identity_schema_version") == PLAN_IDENTITY_SCHEMA_VERSION
        and source.get("migration_evidence_digest") == evidence_digest
        and source.get("subscription_tier") == target_plan
    )


def _beneficiaries(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, (list, tuple)):
        return None
    result: list[str] = []
    for beneficiary in value:
        if (
            not isinstance(beneficiary, str)
            or not beneficiary
            or beneficiary != beneficiary.strip()
            or len(beneficiary) > MAX_COORDINATE_LENGTH
        ):
            return None
        result.append(beneficiary)
    if len(set(result)) != len(result):
        return None
    return tuple(result)


def _beneficiary_scope_matches(
    target_plan: BillingPlanId,
    beneficiaries: tuple[str, ...] | None,
) -> bool:
    if beneficiaries is None:
        return False
    if target_plan is BillingPlanId.FAMILY:
        return 1 <= len(beneficiaries) <= 3
    return len(beneficiaries) == 1


def _valid_first_activation(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _canonical_plan(value: object) -> BillingPlanId:
    if not isinstance(value, str):
        raise ValueError("canonical billing plan is invalid")
    try:
        return BillingPlanId(value)
    except ValueError as exc:
        raise ValueError("canonical billing plan is invalid") from exc


def _safe_source_plan(value: object) -> str:
    return value if isinstance(value, str) and value else "malformed"


def _non_production_environment(value: object) -> str:
    if (
        not isinstance(value, str)
        or not _ENVIRONMENT_PATTERN.fullmatch(value)
        or value in _PRODUCTION_ENVIRONMENTS
    ):
        raise MigrationBlockedError("production migration is refused")
    return value


def _source_sha(value: object) -> str:
    if not isinstance(value, str) or not _SOURCE_SHA_PATTERN.fullmatch(value):
        raise ValueError("migration source SHA is invalid")
    return value


def _required_digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        raise MigrationBlockedError("migration digest is invalid")
    return value


def _validated_applied_at(value: object) -> str:
    if not isinstance(value, str) or not _valid_first_activation(value):
        raise MigrationBlockedError("migration applied time is invalid")
    return value


def _digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("non-finite migration evidence is invalid")
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ValueError("migration evidence keys are invalid")
            result[key] = _json_safe(nested)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(nested) for nested in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_json_safe(nested) for nested in value), key=repr)
    raise ValueError("migration evidence value is invalid")


def _verify_redacted_tree(value: object, *, key: str = "") -> None:
    normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
    if normalized_key in _RECEIPT_FORBIDDEN_KEYS:
        raise MigrationBlockedError("migration preview receipt contains private fields")
    if isinstance(value, dict):
        for nested_key, nested in value.items():
            if not isinstance(nested_key, str):
                raise MigrationBlockedError("migration preview receipt schema is invalid")
            _verify_redacted_tree(nested, key=nested_key)
    elif isinstance(value, list):
        for nested in value:
            _verify_redacted_tree(nested, key=key)
    elif isinstance(value, str):
        lowered = value.lower()
        if (
            "@" in value
            or lowered.startswith(("price_", "sub_", "cus_", "sk_", "pk_"))
            or "private-canary" in lowered
        ):
            raise MigrationBlockedError("migration preview receipt contains private values")


class _RedactedArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> Never:
        self.exit(2, f"{self.prog}: error: plan migration input is invalid\n")


def _load_local_inventory(
    path: str | Path,
) -> tuple[
    tuple[PlanMigrationCoordinate, ...],
    dict[str, str],
    LocalInventoryRepository,
    str,
]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("plan migration input is invalid") from exc
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion",
        "sourceSha",
        "pricePlanById",
        "sources",
    }:
        raise ValueError("plan migration input is invalid")
    if document.get("schemaVersion") != INPUT_SCHEMA_VERSION:
        raise ValueError("plan migration input is invalid")
    source_sha = _source_sha(document.get("sourceSha"))
    raw_prices = document.get("pricePlanById")
    raw_sources = document.get("sources")
    if not isinstance(raw_prices, dict) or not isinstance(raw_sources, list):
        raise ValueError("plan migration input is invalid")
    prices: dict[str, str] = {}
    for price_id, plan in raw_prices.items():
        if not isinstance(price_id, str) or not isinstance(plan, str):
            raise ValueError("plan migration input is invalid")
        prices[price_id] = plan
    coordinates: list[PlanMigrationCoordinate] = []
    sources: dict[tuple[str, str], dict[str, object]] = {}
    for entry in raw_sources:
        if not isinstance(entry, dict) or set(entry) != {"coordinate", "row"}:
            raise ValueError("plan migration input is invalid")
        raw_coordinate = entry.get("coordinate")
        row = entry.get("row")
        if (
            not isinstance(raw_coordinate, dict)
            or set(raw_coordinate) != {"pk", "sk"}
            or not isinstance(row, dict)
        ):
            raise ValueError("plan migration input is invalid")
        coordinate = PlanMigrationCoordinate(
            pk=raw_coordinate.get("pk"),
            sk=raw_coordinate.get("sk"),
        )
        coordinates.append(coordinate)
        sources[(coordinate.pk, coordinate.sk)] = row
    return (
        _validated_coordinates(coordinates),
        prices,
        LocalInventoryRepository(sources),
        source_sha,
    )


def _event_price_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("plan migration input is invalid")
    result: dict[str, str] = {}
    for price_id, plan in value.items():
        if not isinstance(price_id, str) or not isinstance(plan, str):
            raise ValueError("plan migration input is invalid")
        result[price_id] = plan
    _validated_price_plan_map(result)
    return result


def _event_coordinates(value: object) -> tuple[PlanMigrationCoordinate, ...]:
    if not isinstance(value, list):
        raise ValueError("plan migration input is invalid")
    coordinates: list[PlanMigrationCoordinate] = []
    for raw_coordinate in value:
        if not isinstance(raw_coordinate, dict) or set(raw_coordinate) != {"pk", "sk"}:
            raise ValueError("plan migration input is invalid")
        coordinates.append(
            PlanMigrationCoordinate(
                pk=raw_coordinate.get("pk"),
                sk=raw_coordinate.get("sk"),
            )
        )
    return _validated_coordinates(coordinates)


def _event_operator_dispositions(
    value: object,
) -> dict[str, PlanMigrationOperatorDisposition]:
    if not isinstance(value, list):
        raise ValueError("plan migration input is invalid")
    result: dict[str, PlanMigrationOperatorDisposition] = {}
    for raw_disposition in value:
        if not isinstance(raw_disposition, dict) or set(raw_disposition) != {
            "coordinateDigest",
            "targetPlan",
            "evidenceDigest",
        }:
            raise ValueError("plan migration input is invalid")
        coordinate_digest = raw_disposition.get("coordinateDigest")
        target_plan = raw_disposition.get("targetPlan")
        evidence_digest = raw_disposition.get("evidenceDigest")
        if not all(
            isinstance(field, str)
            for field in (coordinate_digest, target_plan, evidence_digest)
        ):
            raise ValueError("plan migration input is invalid")
        disposition = PlanMigrationOperatorDisposition(
            coordinate_digest=coordinate_digest,
            target_plan=target_plan,
            evidence_digest=evidence_digest,
        )
        if coordinate_digest in result:
            raise ValueError("plan migration input is invalid")
        result[coordinate_digest] = disposition
    return result


def _parser() -> argparse.ArgumentParser:
    parser = _RedactedArgumentParser(description="Preview or apply a bounded plan migration.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preview = subparsers.add_parser("preview")
    preview.add_argument(
        "--environment",
        default=os.environ.get("STOA_BILLING_MIGRATION_ENVIRONMENT", ""),
    )
    preview.add_argument(
        "--input",
        default=os.environ.get("STOA_BILLING_MIGRATION_INPUT", ""),
    )
    preview.add_argument(
        "--output",
        default="docs/security/phase-476-plan-migration-preview.json",
    )
    apply = subparsers.add_parser("apply")
    apply.add_argument(
        "--environment",
        default=os.environ.get("STOA_BILLING_MIGRATION_ENVIRONMENT", ""),
    )
    apply.add_argument(
        "--input",
        default=os.environ.get("STOA_BILLING_MIGRATION_INPUT", ""),
    )
    apply.add_argument("--preview-digest", required=True)
    apply.add_argument("--dispositions", required=True)
    apply.add_argument("--applied-at", required=True)
    verify = subparsers.add_parser("verify-preview")
    verify.add_argument("--results", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv) if argv is not None else list(os.sys.argv[1:])
    if not arguments or arguments[0].startswith("-"):
        arguments.insert(0, "preview")
    parser = _parser()
    args = parser.parse_args(arguments)
    try:
        if args.command == "verify-preview":
            result = verify_preview_receipt(args.results)
            print(
                json.dumps(
                    {
                        "status": result["status"],
                        "previewDigest": result["previewDigest"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        if not args.input:
            raise ValueError("plan migration input is invalid")
        coordinates, prices, repository, source_sha = _load_local_inventory(args.input)
        migration_preview = preview_plan_identity_migration(
            coordinates,
            environment=args.environment,
            price_plan_by_id=prices,
            repository=repository,
            source_sha=source_sha,
        )
        if args.command == "apply":
            dispositions_document = json.loads(args.dispositions)
            dispositions = _event_operator_dispositions(dispositions_document)
            result = apply_plan_identity_migration(
                migration_preview,
                preview_digest=args.preview_digest,
                operator_dispositions=dispositions,
                repository=repository,
                environment=args.environment,
                applied_at=args.applied_at,
            )
            print(json.dumps(result.public_dict(), sort_keys=True))
            return 0
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(migration_preview.public_receipt(), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "status": migration_preview.public_receipt()["status"],
                    "previewDigest": migration_preview.preview_digest,
                    "output": str(output_path),
                },
                sort_keys=True,
            )
        )
        return 0
    except (json.JSONDecodeError, MigrationBlockedError, ValueError):
        parser.error("plan migration input is invalid")


if __name__ == "__main__":
    raise SystemExit(main())
