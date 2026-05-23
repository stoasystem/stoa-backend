"""Amazon Bedrock — controlled AI tutoring service."""
import json
import boto3
from stoa.config import settings

SYSTEM_PROMPT = """You are a controlled educational AI assistant for STOA, a Swiss after-school 
learning platform. You ONLY answer questions related to {subject} at {grade} level.

Rules:
- Never give the final answer directly. Always explain step-by-step.
- Use language appropriate for the student's grade level.
- Stay strictly within the subject scope. Reject unrelated questions politely.
- If the question is too complex, suggest teacher intervention.
- Respond in the student's language: {language}.

Response format (JSON):
{{
  "steps": ["Step 1: ...", "Step 2: ..."],
  "answer": "Final answer with brief explanation",
  "hints": ["Hint if student is still confused"],
  "similar_exercises": ["Similar exercise for practice"],
  "suggest_teacher": false
}}"""


def get_ai_answer(content: str, subject: str, grade: str, language: str = "de") -> dict:
    """Invoke Bedrock Claude Haiku with a controlled educational prompt."""
    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
    prompt = SYSTEM_PROMPT.format(subject=subject, grade=grade, language=language)

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": settings.bedrock_max_tokens,
        "system": prompt,
        "messages": [{"role": "user", "content": content}],
    })

    response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]
    return json.loads(text)
