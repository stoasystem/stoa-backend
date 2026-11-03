"""The question's own reads of what it committed: the student message, its attachments.

Moved out of the transcript module (#226) when the conversation's reads went to
`learning_session`. `_stored_student_message` reads back the message row a
command committed and checks it against that command, `_validate_replay_attachment`
checks the attachments it names, and `_conversation_repository_call` is the
question's mapping of repository failures to its public errors; all three are
the question's, not the session's.
"""
from typing import Any

from stoa.db.dynamodb import stored_int
from stoa.db.repositories import attachment_repo
from stoa.models.attachment import AttachmentSummary
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import attachment_service
from stoa.services.ask_question.models import MessageQuote, stored_quote
from stoa.services import learning_session


def _validate_replay_attachment(
    item: Any, *, attachment_id: str, owner_id: str
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    text_fields = (
        "immutable_object_key",
        "immutable_version_id",
        "immutable_etag",
        "detected_type",
        "original_filename",
    )
    checksum = item.get("content_sha256")
    source_fingerprint = item.get("source_fingerprint")
    if (
        item.get("PK") != attachment_repo.attachment_key(attachment_id)["PK"]
        or item.get("SK") != "META"
        or item.get("attachment_id") != attachment_id
        or item.get("owner_id") != owner_id
        or item.get("student_id") != owner_id
        or item.get("status") != "active"
        or item.get("entity_type") != "attachment"
        or item.get("schema_version") != "attachment.v1"
        or any(
            not isinstance(item.get(field), str) or not item[field]
            for field in text_fields
        )
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or any(value not in "0123456789abcdef" for value in checksum)
        or (stored_length := stored_int(item.get("content_length"))) is None
        or stored_length <= 0
        or (
            source_fingerprint is not None
            and (
                not isinstance(source_fingerprint, str)
                or len(source_fingerprint) != 64
                or any(value not in "0123456789abcdef" for value in source_fingerprint)
            )
        )
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_NOT_FOUND)
    return item


def _conversation_repository_call(
    operation, *, conflict_code: AttachmentErrorCode = AttachmentErrorCode.UPLOAD_NOT_FOUND
):
    """Keep conversation repository transport behind one closed public boundary."""
    try:
        return operation()
    except AttachmentDecisionError:
        raise
    except attachment_repo.AttachmentTransactionError as exc:
        code = {
            attachment_repo.AttachmentTransactionOutcome.QUOTA_EXCEEDED: (
                AttachmentErrorCode.STORAGE_QUOTA_EXCEEDED
            ),
            attachment_repo.AttachmentTransactionOutcome.RETRYABLE_DEPENDENCY: (
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ),
            attachment_repo.AttachmentTransactionOutcome.CONCEALED_RESOURCE_CONFLICT: (
                conflict_code
            ),
        }[exc.outcome]
        raise AttachmentDecisionError(code) from None
    except attachment_repo.AttachmentRepositoryConflict as exc:
        if exc.category == "dependency_failure":
            raise AttachmentDecisionError(
                AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
            ) from None
        raise AttachmentDecisionError(conflict_code) from None
    except Exception:
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        ) from None


def _stored_student_message(
    *,
    conv_id: str,
    student_id: str,
    student_msg_id: str,
    created_at: str,
    expected_content: str | None,
    table: Any,
    expected_quote: MessageQuote | None = None,
) -> tuple[str, list, list[AttachmentSummary], MessageQuote | None]:
    """Read back a committed student message and its attachments, checked.

    Returns its content, the attachments as generation prepares them, their
    summaries and the quote stored with it. `expected_content` and
    `expected_quote` are the request's, when there is a request.
    """
    # The session checks the row is a message of this conversation and the
    # student's (#227); what is left is the question's own.
    stored_student = _conversation_repository_call(
        lambda: learning_session.committed_message(
            conv_id, student_msg_id, student_id=student_id
        )
    )
    if (
        stored_student.get("role") != "student"
        or (
            expected_content is not None
            and stored_student.get("content") != expected_content
        )
        or stored_student.get("created_at") != created_at
    ):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    raw_attachment_ids = stored_student.get("attachment_ids", [])
    if (
        not isinstance(raw_attachment_ids, list)
        or any(
            not isinstance(value, str) or not value
            for value in raw_attachment_ids
        )
        or len(set(raw_attachment_ids)) != len(raw_attachment_ids)
    ):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
        )
    attachment_ids = list(raw_attachment_ids)
    stored_attachments = _conversation_repository_call(
        lambda: attachment_repo.get_attachments(attachment_ids, table=table)
    )
    if len(stored_attachments) != len(attachment_ids) or set(
        stored_attachments
    ) != set(attachment_ids):
        raise AttachmentDecisionError(
            AttachmentErrorCode.UPLOAD_NOT_FOUND
        )
    prepared = [
        (
            "attachment",
            _validate_replay_attachment(
                stored_attachments[value],
                attachment_id=value,
                owner_id=student_id,
            ),
        )
        for value in attachment_ids
    ]
    attachments = attachment_service.attachment_summaries_for_records(
        attachment_ids, stored_attachments
    )
    raw_quote = stored_student.get("quote")
    quote = stored_quote(raw_quote)
    if (raw_quote is not None and quote is None) or (
        expected_quote is not None and quote != expected_quote
    ):
        raise AttachmentDecisionError(AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE)
    return str(stored_student["content"]), prepared, attachments, quote
