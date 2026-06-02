"""SQS + SES — teacher queue and email notifications."""
import json
import boto3
from stoa.config import settings


def enqueue_teacher_request(question_id: str, student_id: str, subject: str) -> None:
    """Push a teacher-escalation event to the SQS FIFO queue."""
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    sqs.send_message(
        QueueUrl=settings.teacher_queue_url,
        MessageBody=json.dumps({
            "question_id": question_id,
            "student_id": student_id,
            "subject": subject,
        }),
        MessageGroupId=subject,
        MessageDeduplicationId=question_id,
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
