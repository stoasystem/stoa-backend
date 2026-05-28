"""Amazon Bedrock — controlled AI tutoring service."""
import json
import logging
import re
import boto3
from stoa.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a controlled educational AI assistant for STOA, a Swiss after-school \
learning platform. You ONLY answer questions related to {subject} at {grade} level.

Rules:
- Never give the final answer directly. Always explain step-by-step.
- Use language appropriate for the student's grade level.
- Stay strictly within the subject scope. Reject unrelated questions politely.
- If the question is too complex, suggest teacher intervention.
- Respond in the student's language: {language}.

IMPORTANT: Respond ONLY with valid JSON (no markdown code blocks, no extra text):
{{"steps":["Step 1: ..."],"answer":"Final answer","hints":["Hint..."],"similar_exercises":["Exercise..."],"suggest_teacher":false}}"""


def _parse_ai_response(text: str) -> dict:
    """Parse AI response, handling possible markdown code block wrappers."""
    # Try direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try stripping markdown code block
    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip())
    stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Try extracting the first JSON object found in text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # If all parsing fails, return the text as the answer field
    logger.warning("Could not parse AI response as JSON, using raw text: %r", text[:200])
    return {"steps": [], "answer": text, "hints": [], "similar_exercises": [], "suggest_teacher": False}


def get_ai_answer(content: str, subject: str, grade: str, language: str = "de") -> dict:
    """Invoke Bedrock Claude with a controlled educational prompt."""
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    prompt = SYSTEM_PROMPT.format(subject=subject, grade=grade, language=language)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": settings.bedrock_max_tokens,
        "system": prompt,
        "messages": [{"role": "user", "content": content}],
    })

    logger.info("Calling Bedrock model: %s", settings.bedrock_model_id)
    response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    logger.info("Bedrock response received, length=%d", len(text))
    return _parse_ai_response(text)
