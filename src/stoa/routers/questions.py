"""Question routes: reporting a question's content for moderation.

The old "submit a question" route group - submitting, reading, asking a
teacher and rating a question - was retired in #148: questions are asked in a
learning conversation (`conversations`). Reporting stays, because a teacher
reports a student's contribution from a help request, and a help request is
read as a question row.
"""
from fastapi import APIRouter, Depends, status

from stoa.deps import get_actor
from stoa.models.moderation import ModerationCaseResponse, ModerationReportRequest
from stoa.security.authorization import AuthorizationAction, AuthorizedResource
from stoa.security.identity import Actor
from stoa.security.route_authorization import (
    QUESTION_CONTENT_READ,
    authorized_question_dependency,
)
from stoa.services import moderation_service

router = APIRouter()


@router.post(
    "/{question_id}/reports",
    response_model=ModerationCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_question_content(
    body: ModerationReportRequest,
    authorized: AuthorizedResource = Depends(
        authorized_question_dependency(
            action=AuthorizationAction.CREATE, purposes=QUESTION_CONTENT_READ
        )
    ),
    actor: Actor = Depends(get_actor),
):
    """Create a moderation case for reportable question content."""
    return moderation_service.create_case(
        authorized.ref.resource_id,
        body,
        {"sub": actor.user_id, "role": actor.role.value},
        question=dict(authorized.value),
    )
