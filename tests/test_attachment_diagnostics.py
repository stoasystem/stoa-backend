"""What an attachment failure tells the operator, and what it keeps from them.

Every redacted failure still names its cause and the line that decided it, at a
level that matches whether anyone but the student can act on it; a rejected
transaction is described by its shape and the provider's rule, never by whose
rows it held. Moved here from `test_attachment_security.py` (#254).
"""

import logging
import sys

from botocore.exceptions import ClientError
from fastapi import HTTPException
import pytest

from stoa.db.repositories import attachment_repo
from stoa.routers import conversations as conversations_router
from stoa.routers import files as files_router
from stoa.security import attachment_errors
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode


def test_dependency_failure_names_its_cause_and_site(caplog):
    """A 503 the student cannot act on must still leave an operator something.

    Production ran with no application log line from `attachment_repo` at all,
    so every `upload_service_unavailable` looked alike and the cause had to be
    inferred from black-box probes. The traceback is deliberately dropped by
    `from None`, which is why the cause is read while it is still in flight.
    """
    with caplog.at_level(logging.INFO, logger=attachment_repo.__name__):
        try:
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "Scan"
            )
        except ClientError:
            with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
                raised_on = sys._getframe().f_lineno + 1
                raise attachment_repo.AttachmentRepositoryConflict("dependency_failure")

    record = next(
        r for r in caplog.records if "attachment_repository_conflict" in r.getMessage()
    )
    message = record.getMessage()
    assert record.levelno == logging.WARNING
    assert "category=dependency_failure" in message
    assert "cause=ClientError" in message
    assert "detail=ProvisionedThroughputExceededException" in message
    # The site must be the line that raised, not a frame inside the exception
    # itself - the whole point is to replace the traceback `from None` removed.
    assert f"site=test_dependency_failure_names_its_cause_and_site:{raised_on}" in message
    assert "__post_init__" not in message


def test_a_conditional_conflict_does_not_cry_wolf(caplog):
    """The negative control: ordinary control flow must not log as a failure.

    An idempotent replay losing its race raises the same class. If that were a
    warning too, the dependency failures - the ones nobody can otherwise see -
    would be buried under them.
    """
    with caplog.at_level(logging.INFO, logger=attachment_repo.__name__):
        with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
            raise attachment_repo.AttachmentRepositoryConflict("conditional_conflict")

    record = next(
        r for r in caplog.records if "attachment_repository_conflict" in r.getMessage()
    )
    assert record.levelno == logging.INFO
    assert "cause=none" in record.getMessage()


def test_the_boundary_names_the_line_that_decided(caplog):
    """Every redacted failure leaves by one door, so the door is where it is told.

    `complete_upload` alone raises this directly from a dozen places, none of
    which pass through the repository or the gateway wrapper - which is why
    logging those two was not enough and card 127's second fault stayed
    invisible. This exception's own traceback survives `from None`.
    """
    def _decides():
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)

    deciding_line = sys._getframe().f_lineno - 2

    def _deep():
        _decides()
    with caplog.at_level(logging.INFO, logger=attachment_errors.__name__):
        try:
            _deep()
        except AttachmentDecisionError as error:
            error.correlation_id = "corr-1"
            attachment_errors.log_attachment_failure(error, route="files")

    record = next(r for r in caplog.records if "attachment_failure" in r.getMessage())
    message = record.getMessage()
    assert record.levelno == logging.ERROR
    assert "code=upload_service_unavailable status=503" in message
    assert "route=files correlation_id=corr-1" in message
    assert f"attachment_diagnostics.py:{deciding_line}:_decides" in message
    # The caller chain, not only the innermost frame: in production the line
    # that raised is often a shared helper, and which call reached it is the
    # question. Pinning only the last frame would let that be truncated away.
    assert "_decides < " in message
    assert ":_deep" in message


def test_a_failure_the_student_can_act_on_is_not_an_operator_alarm(caplog):
    """The negative control: a 404 is the student's to fix, not an outage."""
    with caplog.at_level(logging.INFO, logger=attachment_errors.__name__):
        try:
            raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
        except AttachmentDecisionError as error:
            attachment_errors.log_attachment_failure(error, route="files")

    record = next(r for r in caplog.records if "attachment_failure" in r.getMessage())
    assert record.levelno == logging.INFO
    assert "code=upload_not_found status=404" in record.getMessage()


def test_both_doors_tell_before_they_answer():
    """The guard for the call sites: a router that stops logging is a silent 503.

    This is the shape card 127 ran into - the repository and the gateway both
    logged, and the subsystem was still dark, because the route the student
    actually hit raised past them both.
    """
    for module, raise_through, route in (
        (files_router, files_router._raise_safe, "files"),
        (conversations_router, conversations_router._raise_attachment, "conversations"),
    ):
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        log = logging.getLogger(attachment_errors.__name__)
        log.addHandler(handler)
        try:
            error = AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
            with pytest.raises(HTTPException) as raised:
                raise_through(error, "corr-door")
        finally:
            log.removeHandler(handler)
        assert raised.value.status_code == 503
        messages = [r.getMessage() for r in records]
        assert any(
            f"attachment_failure code=upload_service_unavailable status=503 route={route}" in m
            and "correlation_id=corr-door" in m
            for m in messages
        ), f"{module.__name__} answered 503 without saying why: {messages}"


def test_a_blanket_handler_still_names_what_it_caught(caplog):
    """`from None` keeps the cause from the student; it must not keep it from us.

    Card 127's second fault - `complete_upload` answering 503 for every upload -
    took two deploys to reach, because each blanket handler had to be taught to
    say so by itself. The cause is still in flight while the decision is being
    constructed, so it is taken there, once, for every site at once.
    """
    with caplog.at_level(logging.INFO, logger=attachment_errors.__name__):
        try:
            raise ClientError({"Error": {"Code": "NoSuchUpload"}}, "CompleteMultipartUpload")
        except ClientError:
            try:
                raise AttachmentDecisionError(
                    AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
                ) from None
            except AttachmentDecisionError as error:
                assert error.internal_detail == "ClientError:NoSuchUpload"
                attachment_errors.log_attachment_failure(error, route="files")

    record = next(r for r in caplog.records if "attachment_failure" in r.getMessage())
    assert "detail=ClientError:NoSuchUpload" in record.getMessage()


def test_a_detail_the_caller_gave_is_not_overwritten():
    """The negative control: an explicit detail wins over whatever is in flight.

    Routes across this codebase already pass `internal_detail=type(exc).__name__`
    by hand. Replacing those would lose the one the author chose.
    """
    try:
        raise ClientError({"Error": {"Code": "NoSuchUpload"}}, "CompleteMultipartUpload")
    except ClientError:
        error = AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_NOT_FOUND, internal_detail="chosen_by_hand"
        )
    assert error.internal_detail == "chosen_by_hand"
    # And outside an `except` block there is nothing to name, so nothing is named.
    assert AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND).internal_detail is None


def test_a_malformed_transaction_is_described_by_shape_not_by_value(caplog):
    """A ValidationException means the request was wrong, so log what it was.

    No retry fixes a malformed request and no condition explains it, and the
    three rules DynamoDB enforces here - one operation per item, at most a
    hundred items, well-formed keys - are all answerable from the shape. What
    must not reach the log is whose rows they were.
    """
    class _Rejecting:
        name = "stoa-main"
        meta = None

        def transact_attachment_write(self, items):
            raise ClientError(
                {
                    "Error": {
                        "Code": "ValidationException",
                        "Message": (
                            "Supplied AttributeValue is empty for key :used of item "
                            "11111111-2222-3333-4444-555555555555"
                        ),
                    }
                },
                "TransactWriteItems",
            )

    owner = "11111111-2222-3333-4444-555555555555"
    same_key = {"PK": f"ATTACHMENT#{owner}", "SK": "META#one"}
    with caplog.at_level(logging.INFO, logger=attachment_repo.__name__):
        with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
            attachment_repo.transact(
                [
                    {"Put": {"Item": {**same_key, "owner_id": owner}}},
                    {"Put": {"Item": {**same_key, "owner_id": owner}}},
                    {"Delete": {"Key": {"PK": f"OWNER#{owner}", "SK": "STORAGE#used"}}},
                ],
                table=_Rejecting(),
            )

    message = next(
        r.getMessage()
        for r in caplog.records
        if "attachment_transaction_rejected" in r.getMessage()
    )
    assert "items=3" in message
    assert "duplicate_keys=1" in message
    assert "Put:ATTACHMENT/META Put:ATTACHMENT/META Delete:OWNER/STORAGE" in message
    # The provider's own words name the rule, with anything id-shaped taken out.
    assert "rule=Supplied AttributeValue is empty for key :used of item <id>" in message
    # The shape, and nothing under it.
    assert owner not in message
    assert "one" not in message.split("shape=")[0]


def test_a_validation_failure_says_which_rule(caplog):
    """A malformed request is only explicable in the provider's own words.

    Reading a conversation that holds an attachment answered 500 and the log
    said `ValidationException` and no more, which names the class of fault and
    not the fault. Scrubbing still applies: the rule, never the rows.
    """
    with caplog.at_level(logging.INFO, logger=attachment_repo.__name__):
        try:
            raise ClientError(
                {
                    "Error": {
                        "Code": "ValidationException",
                        "Message": (
                            "Provided list of item keys contains duplicates for "
                            "11111111-2222-3333-4444-555555555555"
                        ),
                    }
                },
                "BatchGetItem",
            )
        except ClientError:
            with pytest.raises(attachment_repo.AttachmentRepositoryConflict):
                raise attachment_repo.AttachmentRepositoryConflict("dependency_failure") from None

    message = next(
        r.getMessage()
        for r in caplog.records
        if "attachment_repository_conflict" in r.getMessage()
    )
    assert "detail=ValidationException: Provided list of item keys contains duplicates" in message
    assert "11111111-2222-3333-4444-555555555555" not in message
    assert "<id>" in message
