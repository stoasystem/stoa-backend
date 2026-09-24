"""Write the teacher-queue row for escalations made before that row existed.

Between the deploy that gave every student a weekly teacher-support figure and
the deploy that bridged the escalation to the teacher queue, a student could
escalate a conversation successfully and have no teacher ever see it. The
conversation carries the escalation, so the student cannot ask again - the route
answers with the escalation they already have - and nothing else creates the
missing row.

Report only unless `--apply` is passed. The row is built by the same function
the route uses, so a repaired escalation is indistinguishable from a fresh one.
"""

from __future__ import annotations

import argparse
from typing import Any

from stoa.db.dynamodb import get_table
from stoa.db.repositories import account_deletion_repo
from stoa.routers.conversations import _escalated_question_operation


def escalated_conversations(table: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    key = None
    while True:
        kwargs: dict[str, Any] = {
            "FilterExpression": "escalated = :t",
            "ExpressionAttributeValues": {":t": True},
        }
        if key:
            kwargs["ExclusiveStartKey"] = key
        response = table.scan(**kwargs)
        rows.extend(response.get("Items", []))
        key = response.get("LastEvaluatedKey")
        if not key:
            break
    return rows


def missing_queue_row(table: Any, request_id: str) -> bool:
    if not request_id:
        return False
    response = table.get_item(
        Key={"PK": f"QUESTION#{request_id}", "SK": "META"}, ConsistentRead=True
    )
    return response.get("Item") is None


def repair(table: Any, conversation: dict[str, Any], *, apply: bool) -> str:
    request_id = str(conversation.get("escalation_request_id") or "")
    conversation_id = str(conversation.get("conversation_id") or "")
    student_id = str(conversation.get("student_id") or conversation.get("owner_id") or "")
    if not (request_id and conversation_id and student_id):
        return "skipped: incomplete escalation"

    fence = account_deletion_repo.require_active_account_fence(student_id, table=table)
    operation = _escalated_question_operation(
        request_id=request_id,
        conversation=conversation,
        conversation_id=conversation_id,
        student_id=student_id,
        generation=int(fence["generation"]),
        message=str(conversation.get("escalation_message") or ""),
        now=str(conversation.get("escalated_at") or conversation.get("updated_at") or ""),
    )
    if not apply:
        return f"would write QUESTION#{request_id}/META"
    # Create-only, and under the student's account fence: the same two
    # conditions the escalation itself was written under.
    account_deletion_repo.transact(
        [account_deletion_repo.active_fence_condition(student_id, int(fence["generation"])), operation],
        table=table,
    )
    written = table.get_item(
        Key={"PK": f"QUESTION#{request_id}", "SK": "META"}, ConsistentRead=True
    ).get("Item")
    return f"wrote QUESTION#{request_id}/META; status={(written or {}).get('status')}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write; otherwise report only")
    args = parser.parse_args()

    table = get_table()
    conversations = escalated_conversations(table)
    orphans = [
        row
        for row in conversations
        if missing_queue_row(table, str(row.get("escalation_request_id") or ""))
    ]
    print(f"escalated conversations: {len(conversations)}")
    print(f"missing a teacher-queue row: {len(orphans)}")
    for row in orphans:
        print(f"  {row.get('conversation_id')}: {repair(table, row, apply=args.apply)}")
    if orphans and not args.apply:
        print("\nreport only; rerun with --apply to write")


if __name__ == "__main__":
    main()
