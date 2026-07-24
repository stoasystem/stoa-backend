from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import pytest

from stoa.jobs.migrate_billing_plan_identity import (
    MigrationBlockedError,
    PlanMigrationCoordinate,
    PlanMigrationDisposition,
    PlanMigrationOperatorDisposition,
    apply_plan_identity_migration,
    preview_plan_identity_migration,
    verify_preview_receipt,
)


class FakeMigrationRepository:
    def __init__(self, sources: dict[tuple[str, str], dict[str, object]]) -> None:
        self.sources = sources
        self.reads = 0
        self.writes: list[dict[str, object]] = []

    def read_source(self, coordinate: PlanMigrationCoordinate) -> dict[str, object] | None:
        self.reads += 1
        source = self.sources.get((coordinate.pk, coordinate.sk))
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
        source = self.sources[(coordinate.pk, coordinate.sk)]
        if (
            source.get("migration_evidence_digest") == evidence_digest
            and source.get("subscription_tier") == target_plan
            and source.get("plan_identity_schema_version") == 1
        ):
            return "replayed"
        self.writes.append(
            {
                "coordinate": coordinate,
                "expected_source_digest": expected_source_digest,
                "expected_version": expected_version,
                "source_plan": source_plan,
                "target_plan": target_plan,
                "evidence_digest": evidence_digest,
                "applied_at": applied_at,
            }
        )
        source["subscription_tier"] = target_plan
        source["plan_identity_schema_version"] = 1
        source["migration_evidence_digest"] = evidence_digest
        source["migration_source_plan"] = source_plan
        source["migration_review_required"] = False
        source["version"] = expected_version + 1
        return "applied"


def _source(
    *,
    plan: str,
    version: int = 7,
    price_id: str | None = None,
    subscription_id: str | None = None,
    livemode: bool = False,
    beneficiaries: tuple[str, ...] = (),
    first_activation: str | None = "2025-01-01T00:00:00+00:00",
) -> dict[str, object]:
    row: dict[str, object] = {
        "PK": "USER#private-canary",
        "SK": "PROFILE",
        "version": version,
        "role": "student",
        "subscription_tier": plan,
        "plan_beneficiary_ids": list(beneficiaries),
    }
    if first_activation is not None:
        row["first_student_activation_at"] = first_activation
    if price_id is not None or subscription_id is not None:
        row["provider_evidence"] = {
            "price_id": price_id,
            "subscription_id": subscription_id,
            "livemode": livemode,
        }
    return row


def _coordinate() -> PlanMigrationCoordinate:
    return PlanMigrationCoordinate(pk="USER#private-canary", sk="PROFILE")


def _prices() -> dict[str, str]:
    return {
        "price_student_test": "student",
        "price_teacher_test": "teacher_supported",
        "price_family_test": "family",
    }


def test_preview_is_zero_write_and_canonical_target_uses_billing_plan_id() -> None:
    repository = FakeMigrationRepository(
        {(_coordinate().pk, _coordinate().sk): _source(plan="student", beneficiaries=("s1",))}
    )

    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="a" * 40,
    )

    assert preview.candidates[0].disposition is PlanMigrationDisposition.CANONICAL
    assert preview.candidates[0].target_plan == "student"
    assert preview.mutation_count == 0
    assert repository.writes == []


def test_exact_sandbox_price_and_explicit_beneficiary_resolve_legacy_standard() -> None:
    repository = FakeMigrationRepository(
        {
            (_coordinate().pk, _coordinate().sk): _source(
                plan="standard",
                price_id="price_family_test",
                subscription_id="sub_test_private",
                beneficiaries=("s1", "s2"),
            )
        }
    )

    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="staging",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="b" * 40,
    )

    candidate = preview.candidates[0]
    assert candidate.disposition is PlanMigrationDisposition.EXACT_PROVIDER_MATCH
    assert candidate.target_plan == "family"
    assert candidate.migration_review_required is False


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_source(plan="standard"), PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED),
        (
            _source(
                plan="standard",
                price_id="price_family_test",
                subscription_id="sub_test_private",
                beneficiaries=(),
            ),
            PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
        ),
        (
            _source(plan="free", first_activation=None),
            PlanMigrationDisposition.MIGRATION_REVIEW_REQUIRED,
        ),
        (
            _source(
                plan="standard",
                price_id="price_family_test",
                subscription_id="sub_test_private",
                livemode=True,
                beneficiaries=("s1",),
            ),
            PlanMigrationDisposition.MALFORMED,
        ),
    ],
)
def test_ambiguous_missing_trial_and_live_evidence_never_guess(
    source: dict[str, object],
    expected: PlanMigrationDisposition,
) -> None:
    repository = FakeMigrationRepository({(_coordinate().pk, _coordinate().sk): source})

    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="c" * 40,
    )

    candidate = preview.candidates[0]
    assert candidate.disposition is expected
    assert candidate.target_plan is None
    assert candidate.migration_review_required is True
    assert repository.writes == []


def test_apply_blocks_all_rows_until_every_review_disposition_is_evidence_bound() -> None:
    repository = FakeMigrationRepository(
        {
            (_coordinate().pk, _coordinate().sk): _source(
                plan="standard",
                price_id="price_student_test",
                subscription_id="sub_test_private",
                beneficiaries=(),
            )
        }
    )
    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="d" * 40,
    )

    with pytest.raises(MigrationBlockedError, match="operator disposition"):
        apply_plan_identity_migration(
            preview,
            preview_digest=preview.preview_digest,
            operator_dispositions={},
            repository=repository,
            environment="local-test",
            applied_at="2026-07-24T00:00:00+00:00",
        )

    assert repository.writes == []


def test_apply_refuses_wrong_digest_production_and_live_before_any_write() -> None:
    repository = FakeMigrationRepository(
        {(_coordinate().pk, _coordinate().sk): _source(plan="student", beneficiaries=("s1",))}
    )
    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="e" * 40,
    )
    reads_after_preview = repository.reads

    with pytest.raises(MigrationBlockedError, match="digest"):
        apply_plan_identity_migration(
            preview,
            preview_digest="f" * 64,
            operator_dispositions={},
            repository=repository,
            environment="local-test",
            applied_at="2026-07-24T00:00:00+00:00",
        )
    with pytest.raises(MigrationBlockedError, match="production"):
        apply_plan_identity_migration(
            preview,
            preview_digest=preview.preview_digest,
            operator_dispositions={},
            repository=repository,
            environment="production",
            applied_at="2026-07-24T00:00:00+00:00",
        )

    assert repository.reads == reads_after_preview
    assert repository.writes == []


def test_changed_source_is_skipped_and_replay_performs_zero_second_write() -> None:
    repository = FakeMigrationRepository(
        {
            (_coordinate().pk, _coordinate().sk): _source(
                plan="standard",
                price_id="price_student_test",
                subscription_id="sub_test_private",
                beneficiaries=("s1",),
            )
        }
    )
    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="1" * 40,
    )
    repository.sources[(_coordinate().pk, _coordinate().sk)]["version"] = 8

    changed = apply_plan_identity_migration(
        preview,
        preview_digest=preview.preview_digest,
        operator_dispositions={},
        repository=repository,
        environment="local-test",
        applied_at="2026-07-24T00:00:00+00:00",
    )
    assert changed.results[0].disposition is PlanMigrationDisposition.CHANGED_EVIDENCE
    assert repository.writes == []

    fresh = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="1" * 40,
    )
    applied = apply_plan_identity_migration(
        fresh,
        preview_digest=fresh.preview_digest,
        operator_dispositions={},
        repository=repository,
        environment="local-test",
        applied_at="2026-07-24T00:00:00+00:00",
    )
    replayed = apply_plan_identity_migration(
        fresh,
        preview_digest=fresh.preview_digest,
        operator_dispositions={},
        repository=repository,
        environment="local-test",
        applied_at="2026-07-24T00:00:00+00:00",
    )

    assert applied.results[0].disposition is PlanMigrationDisposition.APPLIED
    assert replayed.results[0].disposition is PlanMigrationDisposition.REPLAYED
    assert len(repository.writes) == 1


def test_evidence_bound_operator_disposition_can_resolve_review_row() -> None:
    repository = FakeMigrationRepository(
        {(_coordinate().pk, _coordinate().sk): _source(plan="standard")}
    )
    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="2" * 40,
    )
    candidate = preview.candidates[0]
    disposition = PlanMigrationOperatorDisposition(
        coordinate_digest=candidate.coordinate_digest,
        target_plan="student",
        evidence_digest=candidate.evidence_digest,
    )

    result = apply_plan_identity_migration(
        preview,
        preview_digest=preview.preview_digest,
        operator_dispositions={candidate.coordinate_digest: disposition},
        repository=repository,
        environment="local-test",
        applied_at="2026-07-24T00:00:00+00:00",
    )

    assert result.results[0].disposition is PlanMigrationDisposition.APPLIED
    assert repository.writes[0]["target_plan"] == "student"


def test_receipt_is_redacted_source_bound_and_schema_verified(tmp_path: Path) -> None:
    repository = FakeMigrationRepository(
        {
            (_coordinate().pk, _coordinate().sk): _source(
                plan="standard",
                price_id="price_family_test",
                subscription_id="sub_private_canary",
                beneficiaries=(),
            )
        }
    )
    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="3" * 40,
    )
    receipt = preview.public_receipt()
    encoded = json.dumps(receipt, sort_keys=True)
    path = tmp_path / "preview.json"
    path.write_text(encoded)

    verified = verify_preview_receipt(path)

    assert verified["status"] == "review_required"
    assert verified["sourceSha"] == "3" * 40
    assert "private-canary" not in encoded
    assert "price_family_test" not in encoded
    assert "sub_private_canary" not in encoded
    assert "@" not in encoded


def test_tampered_preview_candidate_is_rejected_before_write() -> None:
    repository = FakeMigrationRepository(
        {(_coordinate().pk, _coordinate().sk): _source(plan="student", beneficiaries=("s1",))}
    )
    preview = preview_plan_identity_migration(
        (_coordinate(),),
        environment="local-test",
        price_plan_by_id=_prices(),
        repository=repository,
        source_sha="4" * 40,
    )
    tampered = replace(preview, candidates=(replace(preview.candidates[0], target_plan="family"),))

    with pytest.raises(MigrationBlockedError, match="integrity"):
        apply_plan_identity_migration(
            tampered,
            preview_digest=tampered.preview_digest,
            operator_dispositions={},
            repository=repository,
            environment="local-test",
            applied_at="2026-07-24T00:00:00+00:00",
        )

    assert repository.writes == []
