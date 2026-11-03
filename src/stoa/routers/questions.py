"""Question routes: reporting a question's content for moderation.

The old "submit a question" route group - submitting, reading, asking a
teacher and rating a question - was retired in #148: questions are asked in a
learning conversation (`conversations`). Reporting stays, because a teacher
reports a student's contribution from a help request, whose id is the
question id (#189, #234).
"""
from fastapi import APIRouter, Depends, HTTPException, status

from stoa.deps import get_actor
from stoa.models.moderation import ModerationCaseResponse, ModerationReportRequest
from stoa.security.authorization import AuthorizationAction, AuthorizedResource
from stoa.security.errors import SecurityDecisionError
from stoa.security.identity import Actor
from stoa.security.request_correlation import get_request_correlation_id
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
    correlation_id: str = Depends(get_request_correlation_id),
):
    """Create a moderation case for reportable question content."""
    try:
        return moderation_service.create_case(
            authorized.ref.resource_id,
            body,
            {"sub": actor.user_id, "role": actor.role.value},
            request=authorized.value,
        )
    except SecurityDecisionError as error:
        # Refused as the authorization above refuses a request it cannot see.
        refusal = SecurityDecisionError(error.code, correlation_id)
        raise HTTPException(
            status_code=refusal.status_code,
            detail=refusal.public_body(),
            headers={"X-Correlation-ID": correlation_id},
        ) from error
