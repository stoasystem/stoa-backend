"""Which inference profile a development script invokes the model through (#612).

Bedrock bills by the profile a call was invoked through. The product's
functions are given their own application inference profile by stoa-infra
(`BEDROCK_INFERENCE_PROFILE_ARN`); a script run from a developer's machine
finds the development one here, by its name, so that what the scripts cost is
booked apart from what students' questions cost. stoa-infra creates both, one
pair per model, tagged `BedrockUse=product` and `BedrockUse=development`, and
names them by the same rule (`profile_name`).

A model that has no development profile (it was never deployed, or the model
is not the one the product answers with) is invoked directly, as before, and
the script says so: the call still works, its cost is only not set apart.
"""

from __future__ import annotations

import re
import sys
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

PRODUCT = "product"
DEVELOPMENT = "development"


def profile_name(use: str, model_id: str) -> str:
    """The name of the application inference profile of `use` for `model_id`.

    stoa-infra names the profiles by this rule (`stacks/api_stack.py`,
    `bedrock_profile_name`); the two must stay the same.
    """
    return f"stoa-{use}-" + re.sub(r"[^0-9A-Za-z]+", "-", model_id).strip("-")


def development_profile(session: Any, *, region: str, model_id: str) -> str:
    """The ARN of the development profile of `model_id`, or `model_id` when there is none.

    `session` is the operator's boto3 session. Says on stderr which of the two
    the script will invoke.
    """
    name = profile_name(DEVELOPMENT, model_id)
    try:
        arn = _find(session.client("bedrock", region_name=region), name)
    except (BotoCoreError, ClientError) as error:
        arn = None
        reason = f"could not be looked up ({type(error).__name__})"
    else:
        reason = "does not exist"
    if arn is None:
        print(
            f"WARNING: the inference profile {name} {reason}; invoking {model_id} directly, "
            "so this run's cost is not booked as development (#612).",
            file=sys.stderr,
        )
        return model_id
    print(f"Invoking {model_id} through the development profile {name}.", file=sys.stderr)
    return arn


def _find(bedrock: Any, name: str) -> str | None:
    token: str | None = None
    while True:
        page = bedrock.list_inference_profiles(
            typeEquals="APPLICATION", **({"nextToken": token} if token else {})
        )
        for profile in page.get("inferenceProfileSummaries") or []:
            if profile.get("inferenceProfileName") == name and profile.get("status") == "ACTIVE":
                arn = profile.get("inferenceProfileArn")
                if isinstance(arn, str) and arn:
                    return arn
        token = page.get("nextToken")
        if not token:
            return None


__all__ = ["DEVELOPMENT", "PRODUCT", "development_profile", "profile_name"]
