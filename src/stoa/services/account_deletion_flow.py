"""Account deletion in three steps, every row handled as the data type catalog says (#641).

A deletion accepted from #641 on carries `flow = CATALOG_FLOW` and the
catalog's hash (`data_catalog.catalog_sha256`), and runs here:

1. **Lock.** The fence already stopped every write behind it when the deletion
   was accepted. The profile becomes its tombstone, which gives the address
   back in the same commit; the sign-in provider's user is signed out and
   deleted, under a revoke debt that records it (`lock_account`).
2. **Rows.** The account's partitions - the ones its id determines and the
   ones registered under it - are read page by page, and each row that names
   the account is handled as its catalog entry says: what it does outside the
   row first (an `Effect`), then the row itself (`Delete`, `Tombstone`, `Scrub`;
   `Keep` leaves it). A pass that read to the end and found a row to handle is
   followed by another; the deletion is done when a whole pass finds none.
   Where a run stopped is written on the command, page by page, and the next
   run carries on from there.
3. **Deliveries.** A push or email a sender still holds, under a live lease,
   is left until the sender lets go: until then a pass is not clean. One the
   provider has already accepted, or may have, is counted on the command as a
   receipt outside the backend's reach.

The catalog's hash seals the deletion: a run that finds the catalog changed
since the deletion was accepted pauses it - writes nothing, logs, and the
scheduled job fails so the alarm on it pages - rather than finish it under
rules it was not accepted with.

Every outside action is safe to run again, and each row's change is
conditional on the row still being the account's, so a run that stopped
anywhere, or a row written while the deletion ran, is met again by a later
pass and settled then.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
import logging
from typing import Any, Final

from stoa import aws, config
from stoa.aws import Kind
from stoa.db import data_catalog
from stoa.db import table as db_table
from stoa.db.dynamodb import stored_int
from stoa.db.repositories import (
    account_deletion_repo,
    attachment_repo,
    curriculum_analytics_repo,
    notification_repo,
    report_repo,
)
from stoa.services import (
    ask_question,
    attachment_service,
    help_requests,
    moderation_service,
    uploads,
)


logger = logging.getLogger(__name__)

CATALOG_FLOW: Final = "catalog.v1"
"""What a command accepted for this flow carries in `flow`."""

PAGE_ROWS: Final = 100
MIN_REMAINING_SECONDS: Final = 60.0
LEASE_SECONDS: Final = 120

# How a row came out of one visit.
DONE: Final = "done"  # handled: deleted, tombstoned or scrubbed
WAIT: Final = "wait"  # not yet: the next pass tries again
READY: Final = "ready"  # (an effect) done outside the row; now change the row

# A delivery a sender holds under this state is on its way to the provider.
_IN_FLIGHT_DELIVERY: Final = "claimed_pre_effect"
_RECEIPT_STATES: Final = frozenset({"accepted", "provider_acceptance_unknown"})
RECEIPT_CLAIM: Final = "outside_backend_purge_authority"


class DeletionPaused(account_deletion_repo.AccountDeletionConflict):
    """A deletion that must not go on: the catalog changed since it was accepted."""


def current_catalog_sha256() -> str:
    return data_catalog.catalog_sha256()


def is_catalog_command(command: Mapping[str, Any]) -> bool:
    return command.get("flow") == CATALOG_FLOW


# -- one row ------------------------------------------------------------------------------


@dataclass(slots=True)
class _Visit:
    """What a run knows while it handles rows: the account, and what it counted."""

    account: str
    generation: int
    now_iso: str
    now_epoch: int
    receipts: Counter[str] = field(default_factory=Counter)
    in_flight: int = 0
    _s3: Any = None
    # Set by an effect, read once the row's own change has gone through.
    receipt: str | None = None
    keep_status: bool = False

    @property
    def s3(self) -> Any:
        if self._s3 is None:
            self._s3 = aws.client(Kind.S3)
        return self._s3

    @property
    def now(self) -> datetime:
        return datetime.fromisoformat(self.now_iso)


Effect = Callable[[Mapping[str, Any], data_catalog.DataType, _Visit], str]
RowChange = Callable[[Mapping[str, Any], _Visit], str]


def _revoke_provider_identity(row: Mapping[str, Any], _kind: Any, visit: _Visit) -> str:
    """Sign out and delete the provider's user the row names, once, under the revoke debt."""
    debt = account_deletion_repo.get_row(
        {"PK": f"USER#{visit.account}", "SK": f"PROVIDER_REVOKE#{visit.generation:020d}"}
    )
    if debt is not None and debt.get("status") == "complete":
        return READY
    username = provider_username([row])
    if username is None:
        return READY
    revoke_provider(
        visit.account, visit.generation, username, now_iso=visit.now_iso
    )
    return READY


def _release_attachment_reference(row: Mapping[str, Any], _kind: Any, visit: _Visit) -> str:
    outcome = attachment_service.release_reference(
        row, s3=visit.s3, settings=config.settings(), now=visit.now
    )
    return DONE if outcome is attachment_service.LeaveOutcome.DONE else WAIT


def _delete_stored_object(row: Mapping[str, Any], kind: Any, visit: _Visit) -> str:
    hook = STORED_OBJECTS[kind.name]
    return hook(row, visit)


def _delete_attachment(row: Mapping[str, Any], visit: _Visit) -> str:
    outcome = attachment_service.delete_attachment(
        row, s3=visit.s3, settings=config.settings(), now=visit.now
    )
    return DONE if outcome is attachment_service.LeaveOutcome.DONE else WAIT


def _clean_upload(row: Mapping[str, Any], visit: _Visit) -> str:
    gone = uploads.leave_for_account_deletion(
        row,
        account_fence_generation=visit.generation,
        s3=visit.s3,
        settings=config.settings(),
        now=visit.now,
    )
    return DONE if gone else WAIT


def _delete_moderation_image(row: Mapping[str, Any], visit: _Visit) -> str:
    # The row's own `student_id` says whose it is (#634 decision 5); the
    # question it was raised on is never read, so a case whose question is
    # already gone is handled like any other (#640).
    moderation_service.delete_case_image(row, s3=visit.s3, settings=config.settings())
    return READY


def _delete_report_object(row: Mapping[str, Any], visit: _Visit) -> str:
    bucket = config.settings().report_artifacts_bucket
    candidate = dict(row)
    if not candidate.get("version_id"):
        body_length = stored_int(candidate.get("body_length"))
        if body_length is None:
            return WAIT
        candidate.update(
            report_repo.reconcile_report_object_version(
                s3_client=visit.s3,
                bucket=bucket,
                object_key=str(candidate["object_key"]),
                operation_id=str(candidate["operation_id"]),
                body_sha256=str(candidate["body_sha256"]),
                body_length=body_length,
            )
        )
    result = report_repo.purge_report_object_intent(
        candidate,
        owner_id=visit.account,
        generation=visit.generation,
        bucket=bucket,
        s3_client=visit.s3,
        now_iso=visit.now_iso,
    )
    # Purged: the report module tombstoned the row itself. A version under
    # legal hold stays, and so does the deletion, until the hold is lifted.
    return DONE if result.get("status") == "purged" else WAIT


def _reconcile_curriculum_signal(row: Mapping[str, Any], _kind: Any, visit: _Visit) -> str:
    # Deletes the signal, takes its counts off the metric and deletes this
    # manifest, in one transaction.
    curriculum_analytics_repo.reconcile_curriculum_signal(
        row, owner_id=visit.account, generation=visit.generation, now_iso=visit.now_iso
    )
    return DONE


def _cancel_inflight_question(row: Mapping[str, Any], _kind: Any, visit: _Visit) -> str:
    ask_question.cancel_for_account_deletion(
        dict(row),
        owner_id=visit.account,
        deletion_generation=visit.generation,
        now_iso=visit.now_iso,
    )
    return READY


def _count_external_delivery(row: Mapping[str, Any], _kind: Any, visit: _Visit) -> str:
    """Wait for a delivery a sender holds; count one a provider has, or may have."""
    status = str(row.get("status") or "")
    if status == _IN_FLIGHT_DELIVERY:
        lease = stored_int(row.get("lease_expires_at"))
        if lease is not None and lease >= visit.now_epoch:
            visit.in_flight += 1
            return WAIT
        # The sender's lease ran out mid-send: the provider may have it.
        visit.receipt = "provider_acceptance_unknown"
        return READY
    if status in _RECEIPT_STATES:
        visit.receipt = status
        visit.keep_status = True
    return READY


def _release_email_claim(_row: Mapping[str, Any], _kind: Any, _visit: _Visit) -> str:
    # Committed with the profile's tombstone (`replace_with_deletion_tombstone`).
    return READY


EFFECTS: Final[Mapping[data_catalog.Effect, Effect]] = {
    "release_email_claim": _release_email_claim,
    "revoke_provider_identity": _revoke_provider_identity,
    "release_attachments": _release_attachment_reference,
    "delete_stored_object": _delete_stored_object,
    "reconcile_curriculum_signal": _reconcile_curriculum_signal,
    "cancel_inflight_question": _cancel_inflight_question,
    "count_external_delivery": _count_external_delivery,
}
"""Each `Effect` of the catalog, done by the module that owns it."""

STORED_OBJECTS: Final[Mapping[str, Callable[[Mapping[str, Any], _Visit], str]]] = {
    "attachment": _delete_attachment,  # "delete one file" (#636)
    "upload_intent": _clean_upload,  # "clean one upload" (#636)
    "moderation_case": _delete_moderation_image,
    "report_object_intent": _delete_report_object,
}
"""Which object `delete_stored_object` deletes, for each type that has it."""


def _scrub_parent_profile(row: Mapping[str, Any], visit: _Visit) -> str:
    account_deletion_repo.scrub_parent_profile_child(
        row, child_user_id=visit.account, generation=visit.generation
    )
    return DONE


def _scrub_question(row: Mapping[str, Any], visit: _Visit) -> str:
    account_deletion_repo.scrub_teacher_question_reference(
        row, teacher_user_id=visit.account, generation=visit.generation
    )
    return DONE


def _scrub_help_request(row: Mapping[str, Any], visit: _Visit) -> str:
    help_requests.scrub_teacher(
        row,
        teacher_id=visit.account,
        generation=visit.generation,
        now=visit.now_iso,
        table=db_table.table(),
    )
    return DONE


def _scrub_notification(row: Mapping[str, Any], visit: _Visit) -> str:
    notification_repo.scrub_notification_identity_references(
        row, owner_id=visit.account, generation=visit.generation
    )
    return DONE


SCRUBS: Final[Mapping[str, RowChange]] = {
    "user_profile": _scrub_parent_profile,
    "question": _scrub_question,
    "help_request": _scrub_help_request,
    "notification_event": _scrub_notification,
}
"""How the account's name is taken out of each type whose catalog entry says `Scrub`."""


def _delete_storage_usage(row: Mapping[str, Any], visit: _Visit) -> str:
    # Only once nothing is counted on it: every file's delete lowers it first.
    deleted = attachment_repo.delete_empty_storage_usage(
        visit.account, account_fence_generation=visit.generation
    )
    return DONE if deleted else WAIT


ROW_DELETES: Final[Mapping[str, RowChange]] = {
    "attachment_storage_usage": _delete_storage_usage,
}
"""A `Delete` its own module does; every other is `delete_owned_row`."""


def _tombstone_profile(row: Mapping[str, Any], visit: _Visit) -> str:
    # The profile's own lifecycle writer (`user_repo.PROFILE_WRITER_REGISTRY`),
    # whose fields are the catalog's and which gives the address back in the
    # same commit.
    account_deletion_repo.replace_with_deletion_tombstone(
        row, user_id=visit.account, generation=visit.generation, now_iso=visit.now_iso
    )
    return DONE


ROW_TOMBSTONES: Final[Mapping[str, RowChange]] = {"user_profile": _tombstone_profile}
"""A `Tombstone` its own module writes; every other is `tombstone_owned_row`."""


def _delete_row(row: Mapping[str, Any], visit: _Visit) -> str:
    try:
        account_deletion_repo.delete_owned_row(
            row, user_id=visit.account, generation=visit.generation
        )
    except account_deletion_repo.AccountDeletionConflict:
        if account_deletion_repo.get_row(row) is not None:
            raise
    return DONE


def _settled(row: Mapping[str, Any]) -> bool:
    """A tombstone a deletion already left, which may still name its owner."""
    return account_deletion_repo.is_deletion_tombstone(row) or row.get("privacy_deleted") is True


def action_for(
    row: Mapping[str, Any], account: str
) -> tuple[data_catalog.DataType, data_catalog.OwnerAction | data_catalog.ReferenceAction] | None:
    """The catalog's action for `row` in `account`'s deletion, or None if there is nothing to do."""
    if _settled(row):
        return None
    kind = data_catalog.data_type_of(row)
    if kind is None or kind.deletion is None:
        return None
    role = data_catalog.role_of(row, account)
    if role is None:
        return None
    action = kind.deletion.owner if role == data_catalog.OWNER else kind.deletion.reference
    if action is None or isinstance(action, data_catalog.Keep):
        return None
    return kind, action


def handle_row(row: Mapping[str, Any], visit: _Visit) -> str | None:
    """Handle one row as the catalog says: None if it asks nothing, else DONE or WAIT."""
    found = action_for(row, visit.account)
    if found is None:
        return None
    kind, action = found
    visit.receipt, visit.keep_status = None, False
    try:
        outcome = _apply(row, kind, action, visit)
    except account_deletion_repo.DeletionCommandClaimLost:
        raise
    except Exception as exc:
        # Left for the next pass, which reads the row again as it stands.
        logger.warning(
            "account_deletion_row_retry entity_type=%s reason=%s",
            kind.name,
            type(exc).__name__,
        )
        return WAIT
    if outcome == DONE and visit.receipt is not None:
        visit.receipts[visit.receipt] += 1
    return outcome


def _apply(
    row: Mapping[str, Any],
    kind: data_catalog.DataType,
    action: data_catalog.OwnerAction | data_catalog.ReferenceAction,
    visit: _Visit,
) -> str:
    if isinstance(action, data_catalog.Scrub):
        return SCRUBS[kind.name](row, visit)
    assert isinstance(action, (data_catalog.Delete, data_catalog.Tombstone))
    for effect in action.effects:
        outcome = EFFECTS[effect](row, kind, visit)
        if outcome != READY:
            return outcome
    if isinstance(action, data_catalog.Delete):
        return ROW_DELETES.get(kind.name, _delete_row)(row, visit)
    own = ROW_TOMBSTONES.get(kind.name)
    if own is not None:
        return own(row, visit)
    account_deletion_repo.tombstone_owned_row(
        row,
        account=visit.account,
        generation=visit.generation,
        keeps=action.keeps,
        now_iso=visit.now_iso,
        keep_status=visit.keep_status,
    )
    return DONE


# -- step 1: lock -------------------------------------------------------------------------


def provider_username(rows: list[Mapping[str, Any]]) -> str | None:
    """The provider user an identity row names: its email, else its subject."""
    return next(
        (
            str(row.get(name)).strip()
            for row in rows
            for name in ("normalized_email", "email", "subject")
            if isinstance(row.get(name), str) and str(row.get(name)).strip()
        ),
        None,
    )


def revoke_provider(account: str, generation: int, username: str, *, now_iso: str) -> None:
    """Sign the provider's user out and delete it, recorded under the revoke debt; repeatable."""
    account_deletion_repo.create_provider_revoke_debt(
        user_id=account, generation=generation, now_iso=now_iso
    )
    settings = config.settings()
    provider = aws.client(Kind.COGNITO)
    account_deletion_repo.require_deletion_account_fence(account, generation)
    try:
        provider.admin_user_global_sign_out(
            UserPoolId=settings.cognito_user_pool_id, Username=username
        )
        account_deletion_repo.require_deletion_account_fence(account, generation)
        provider.admin_delete_user(UserPoolId=settings.cognito_user_pool_id, Username=username)
    except provider.exceptions.UserNotFoundException:
        pass
    account_deletion_repo.complete_provider_revoke_debt(
        user_id=account, generation=generation, now_iso=now_iso
    )


def lock_account(account: str, generation: int, *, now_iso: str, provider: bool) -> None:
    """Step 1: the profile's tombstone and, with `provider`, the sign-in provider's revoke.

    Read from the account's own partition by key, so it is quick whatever the
    size of the table. The identity rows themselves are tombstoned in step 2,
    whose revoke then finds the debt complete. Without `provider` (the API
    function, which holds no Cognito admin rights) only the profile.
    """
    rows = account_deletion_repo.query_account_partition(account)
    profile = next((row for row in rows if row.get("SK") == "PROFILE"), None)
    if (
        profile is not None
        and profile.get("user_id") == account
        and not account_deletion_repo.is_deletion_tombstone(profile)
    ):
        account_deletion_repo.replace_with_deletion_tombstone(
            profile, user_id=account, generation=generation, now_iso=now_iso
        )
    if not provider:
        return
    identities: list[Mapping[str, Any]] = []
    for row in rows:
        if row.get("entity_type") != "user_identity_inventory" or row.get("user_id") != account:
            continue
        binding_pk = row.get("binding_pk")
        if isinstance(binding_pk, str) and binding_pk:
            binding = account_deletion_repo.get_row({"PK": binding_pk, "SK": "BINDING"})
            if binding is not None and binding.get("user_id") == account:
                identities.append(binding)
        identities.append(row)
    username = provider_username(identities)
    if username is not None:
        revoke_provider(account, generation, username, now_iso=now_iso)


# -- the run ------------------------------------------------------------------------------


def _fresh_pass(progress: Mapping[str, Any], *, step: str) -> dict[str, Any]:
    return {
        "step": step,
        "pass": int(stored_int(progress.get("pass")) or 0) + 1,
        "cursor": None,
        "found": 0,
        "waiting": 0,
        "in_flight": 0,
        "receipts": dict(progress.get("receipts") or {}),
    }


def external_receipts(progress: Mapping[str, Any]) -> list[dict[str, Any]]:
    counts = progress.get("receipts") or {}
    return [
        {"channel": "provider", "status": status, "count": int(stored_int(counts[status]) or 0),
         "claim": RECEIPT_CLAIM}
        for status in sorted(counts)
        if stored_int(counts[status])
    ]


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """How one run left a deletion: `complete`, `paused` or `unfinished`."""

    status: str
    passes: int = 0
    pages: int = 0


class CatalogDeletion:
    """Carries one claimed catalog deletion as far as a run's time allows."""

    def __init__(
        self,
        *,
        remaining_seconds: Callable[[], float] | None = None,
        min_remaining_seconds: float = MIN_REMAINING_SECONDS,
        page_rows: int = PAGE_ROWS,
        max_pages: int | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.remaining_seconds = remaining_seconds
        self.min_remaining_seconds = min_remaining_seconds
        self.page_rows = max(int(page_rows), 1)
        # Without a time budget (a test, or a call that is not the scheduled
        # job) a run stops after this many pages instead.
        self.max_pages = max_pages if max_pages is not None else (
            None if remaining_seconds is not None else 1000
        )
        self.clock = now or (lambda: datetime.now(UTC))

    # -- the command and its lease ---------------------------------------------

    def _now(self) -> tuple[str, int]:
        moment = self.clock().astimezone(UTC)
        return moment.isoformat(), int(moment.timestamp())

    def _out_of_time(self, pages: int) -> bool:
        if self.remaining_seconds is not None:
            return self.remaining_seconds() < self.min_remaining_seconds
        return self.max_pages is not None and pages >= self.max_pages

    def _lease_until(self, now_epoch: int) -> int:
        if self.remaining_seconds is None:
            return now_epoch + LEASE_SECONDS
        return now_epoch + max(LEASE_SECONDS, int(max(self.remaining_seconds(), 0.0)) + 30)

    @staticmethod
    def _load(claim: account_deletion_repo.DeletionCommandClaim) -> dict[str, Any]:
        if not claim.user_id:
            raise account_deletion_repo.DeletionCommandClaimLost("claim names no account")
        command = account_deletion_repo.get_deletion_command(claim.user_id, claim.command_id)
        if not command:
            raise account_deletion_repo.DeletionCommandClaimLost("deletion command disappeared")
        return command

    @staticmethod
    def _require_claim(
        command: Mapping[str, Any], claim: account_deletion_repo.DeletionCommandClaim
    ) -> None:
        if (
            command.get("status") != "running"
            or command.get("command_id") != claim.command_id
            or command.get("generation") != claim.generation
            or command.get("lease_owner") != claim.lease_owner
            or command.get("command_version") != claim.command_version
        ):
            raise account_deletion_repo.DeletionCommandClaimLost("deletion claim lost")

    def _release(self, command: Mapping[str, Any], claim: Any) -> None:
        now_iso, now_epoch = self._now()
        try:
            account_deletion_repo.release_deletion_command_claim(
                command, claim=claim, now_epoch=now_epoch, updated_at=now_iso
            )
        except Exception:
            logger.warning("account_deletion_lease_release_failed")

    # -- the steps ----------------------------------------------------------------

    def run_request_side(self, claim: account_deletion_repo.DeletionCommandClaim) -> None:
        """What `DELETE /auth/me` does at once: the profile's tombstone, then the lease back."""
        command = self._load(claim)
        try:
            self._require_claim(command, claim)
            if command.get("catalog_sha256") != current_catalog_sha256():
                return
            now_iso, _ = self._now()
            lock_account(
                str(command["user_id"]),
                int(command["generation"]),
                now_iso=now_iso,
                provider=False,
            )
        finally:
            self._release(command, claim)

    def continue_command(self, claim: account_deletion_repo.DeletionCommandClaim) -> RunOutcome:
        command = self._load(claim)
        if command.get("status") == "complete":
            return RunOutcome("complete")
        self._require_claim(command, claim)
        if command.get("catalog_sha256") != current_catalog_sha256():
            logger.error(
                "account_deletion_paused reason=catalog_changed command_id=%s",
                command.get("command_id"),
            )
            self._release(command, claim)
            return RunOutcome("paused")
        self._claim = claim
        try:
            outcome = self._run(command)
        except BaseException:
            self._give_back()
            raise
        if outcome.status != "complete":
            self._give_back()
        return outcome

    def _give_back(self) -> None:
        """The lease back, so the next run need not wait for it to run out."""
        try:
            command = self._load(self._claim)
        except Exception:
            return
        if command.get("status") == "running":
            self._release(command, self._claim)

    def _persist(self, command: Mapping[str, Any], progress: Mapping[str, Any]) -> None:
        now_iso, now_epoch = self._now()
        # `open` until a run says it stopped between pages (`_run`).
        self._claim = account_deletion_repo.persist_deletion_progress(
            command,
            {"open": True, **progress, "updated_at": now_iso},
            claim=self._claim,
            now_epoch=now_epoch,
            now_iso=now_iso,
        )

    def _renew(self, command: Mapping[str, Any]) -> None:
        now_iso, now_epoch = self._now()
        self._claim = account_deletion_repo.renew_deletion_command_claim(
            command,
            claim=self._claim,
            now_epoch=now_epoch,
            lease_expires_at=self._lease_until(now_epoch),
            now_iso=now_iso,
        )

    def _run(self, command: dict[str, Any]) -> RunOutcome:
        account = account_deletion_repo.deletion_account(command["user_id"])
        generation = int(command["generation"])
        progress: dict[str, Any] = dict(command.get("deletion_progress") or {})
        was_open = progress.pop("open", False) is True
        self._renew(command)
        if progress.get("step") in (None, "lock"):
            now_iso, _ = self._now()
            lock_account(account, generation, now_iso=now_iso, provider=True)
            progress = _fresh_pass({}, step="rows")
            self._persist(command, progress)
        elif was_open:
            # The run before stopped without saying so: it may have changed
            # rows on the page it was on without counting them, so this pass
            # cannot be the clean one. One more pass settles it.
            progress["found"] = int(stored_int(progress.get("found")) or 0) + 1
        scope = account_deletion_repo.RegistryScope(
            account, account_deletion_repo.owner_partitions(account)
        )
        pages = passes = 0
        while not self._out_of_time(pages):
            self._renew(command)
            now_iso, now_epoch = self._now()
            visit = _Visit(account, generation, now_iso, now_epoch)
            cursor = progress.get("cursor")
            page = next(
                account_deletion_repo.registry_pages(
                    scope,
                    start=dict(cursor) if isinstance(cursor, Mapping) else None,
                    table=db_table.table(),
                    Limit=self.page_rows,
                )
            )
            pages += 1
            found = waiting = 0
            for row in page.items:
                outcome = handle_row(row, visit)
                if outcome is None:
                    continue
                found += 1
                waiting += outcome == WAIT
            receipts = Counter(
                {key: int(stored_int(value) or 0) for key, value in (progress.get("receipts") or {}).items()}
            )
            receipts.update(visit.receipts)
            progress = {
                **progress,
                "cursor": dict(page.last_key) if page.last_key is not None else None,
                "found": int(stored_int(progress.get("found")) or 0) + found,
                "waiting": int(stored_int(progress.get("waiting")) or 0) + waiting,
                "in_flight": int(stored_int(progress.get("in_flight")) or 0) + visit.in_flight,
                "receipts": dict(receipts),
            }
            if page.last_key is not None:
                self._persist(command, progress)
                continue
            passes += 1
            logger.info(
                "account_deletion_pass_finished command_id=%s pass=%s found=%s waiting=%s "
                "in_flight=%s",
                command.get("command_id"),
                progress.get("pass"),
                progress["found"],
                progress["waiting"],
                progress["in_flight"],
            )
            if progress["found"] == 0:
                self._finalize(command, progress)
                return RunOutcome("complete", passes, pages)
            stalled = progress["waiting"] == progress["found"]
            only_deliveries = progress["in_flight"] > 0 and progress["in_flight"] == progress["found"]
            progress = _fresh_pass(progress, step="deliveries" if only_deliveries else "rows")
            if stalled:
                # Nothing in this pass could move; a later run tries again.
                break
            self._persist(command, progress)
        # Stopped between pages, everything read so far counted.
        self._persist(command, {**progress, "open": False})
        return RunOutcome("unfinished", passes, pages)

    def _finalize(self, command: Mapping[str, Any], progress: Mapping[str, Any]) -> None:
        account = str(command["user_id"])
        generation = int(command["generation"])
        now_iso, now_epoch = self._now()
        # A revoke debt opened for an identity that had no provider user.
        account_deletion_repo.close_unused_provider_revoke_debt(
            user_id=account, generation=generation, closed_at=now_iso
        )
        fence = account_deletion_repo.require_deletion_account_fence(account, generation)
        current = self._load(self._claim)
        self._require_claim(current, self._claim)
        account_deletion_repo.finalize_catalog_deletion(
            command=current,
            fence=fence,
            claim=self._claim,
            catalog_sha256=current_catalog_sha256(),
            external_receipts=external_receipts(progress),
            now_epoch=now_epoch,
            now_iso=now_iso,
        )
        logger.info("account_deletion_complete command_id=%s", command.get("command_id"))
        try:
            account_deletion_repo.delete_owner_registry(account)
        except Exception:
            # Bookkeeping rows the daily sweep reports; nothing private.
            logger.warning("account_deletion_registry_cleanup_failed")


def check_hooks() -> None:
    """Every action the catalog names has the code that does it (gated by a test)."""
    missing: list[str] = []
    for kind in (*data_catalog.CATALOG.values(), *data_catalog.UNTYPED):
        deletion = kind.deletion
        if deletion is None:
            continue
        for action in (deletion.owner, deletion.reference):
            if isinstance(action, data_catalog.Scrub) and kind.name not in SCRUBS:
                missing.append(f"{kind.name}: scrub")
            if isinstance(action, (data_catalog.Delete, data_catalog.Tombstone)):
                for effect in action.effects:
                    if effect not in EFFECTS:
                        missing.append(f"{kind.name}: {effect}")
                    if effect == "delete_stored_object" and kind.name not in STORED_OBJECTS:
                        missing.append(f"{kind.name}: stored object")
    if missing:
        raise RuntimeError("catalog actions without code: " + ", ".join(missing))
