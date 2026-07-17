"""SQS + SES — teacher queue and email notifications."""
import json
from datetime import UTC, datetime
from uuid import uuid4
import boto3
from stoa.config import settings
from stoa.db.repositories import account_deletion_repo, report_repo


def require_active_account_fence(owner_id: str, generation: int) -> bool:
    try:
        account_deletion_repo.require_active_account_fence(owner_id, generation)
    except account_deletion_repo.AccountDeletionConflict:
        return False
    return True


def enqueue_teacher_request(
    *, question_id: str, operation_id: str, generation: int, owner_id: str | None = None
) -> None:
    """Push only opaque fenced coordinates to the teacher FIFO queue."""
    if type(generation) is not int or generation <= 0:
        raise RuntimeError("teacher escalation generation is required")
    fence_owner = owner_id or operation_id
    if not require_active_account_fence(fence_owner, generation):
        raise RuntimeError("teacher escalation owner is fenced")
    if owner_id:
        account_deletion_repo.create_teacher_escalation_intent(
            owner_id=owner_id,
            question_id=question_id,
            operation_id=operation_id,
            generation=generation,
        )
        if not require_active_account_fence(owner_id, generation):
            raise RuntimeError("teacher escalation owner is fenced")
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    sqs.send_message(
        QueueUrl=settings.teacher_queue_url,
        MessageBody=json.dumps({
            "operation_id": operation_id,
            "question_id": question_id,
            "generation": generation,
        }),
        MessageGroupId=operation_id,
        MessageDeduplicationId=operation_id,
    )


def send_weekly_report_email(
    parent_email: str,
    report_html: str,
    *,
    subject: str | None = None,
    ses_client=None,
) -> None:
    """Send the weekly report to a parent via SES."""
    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    ses.send_email(
        Source="noreply@stoaedu.ch",
        Destination={"ToAddresses": [parent_email]},
        Message={
            "Subject": {"Data": subject or "STOA - Wochenbericht Ihres Kindes"},
            "Body": {"Html": {"Data": report_html}},
        },
    )


def send_fenced_weekly_report_email(
    parent_email: str,
    report_html: str,
    *,
    owner_id: str,
    generation: int,
    report_id: str,
    subject: str | None = None,
    operation_id: str | None = None,
    ses_client=None,
    table=None,
) -> str:
    """Send once only after durable intent, claim, and immediate fence checks."""
    operation = operation_id or uuid4().hex
    subject_value = subject or "STOA - Wochenbericht Ihres Kindes"
    now_iso = datetime.now(UTC).isoformat()
    intent = report_repo.register_report_email_intent(
        owner_id=owner_id,
        generation=generation,
        operation_id=operation,
        report_id=report_id,
        recipient=parent_email,
        subject=subject_value,
        body=report_html,
        now_iso=now_iso,
        table=table,
    )
    report_repo.claim_report_email_intent(intent, lease_id=uuid4().hex, table=table)
    account_deletion_repo.require_active_account_fence(owner_id, generation, table=table)
    ses = ses_client or boto3.client("ses", region_name=settings.aws_region)
    response = None
    error = None
    try:
        response = ses.send_email(
            Source="noreply@stoaedu.ch",
            Destination={"ToAddresses": [parent_email]},
            Message={
                "Subject": {"Data": subject_value},
                "Body": {"Html": {"Data": report_html}},
            },
        )
    except Exception as exc:
        error = exc
    return report_repo.classify_report_delivery_outcome(response=response, error=error)
