from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    environment: str = "development"
    cors_origins: List[str] = [
        "http://localhost:5173",
        "https://app.stoaedu.ch",
    ]

    # AWS
    aws_region: str = "eu-central-2"
    aws_account_id: str = ""

    # DynamoDB
    dynamodb_table_name: str = "stoa-main"

    # S3
    s3_images_bucket: str = "stoa-images"
    s3_reports_bucket: str = "stoa-reports"
    s3_presign_expiry_seconds: int = 300

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_student_client_id: str = ""
    cognito_parent_client_id: str = ""
    cognito_teacher_client_id: str = ""
    cognito_admin_client_id: str = ""

    @property
    def cognito_jwks_url(self) -> str:
        return (
            f"https://cognito-idp.{self.aws_region}.amazonaws.com"
            f"/{self.cognito_user_pool_id}/.well-known/jwks.json"
        )

    # Bedrock
    bedrock_model_id: str = "anthropic.claude-haiku-20240307-v1:0"
    bedrock_max_tokens: int = 2048

    # Limits (per role per day)
    free_tier_daily_question_limit: int = 5
    standard_tier_daily_question_limit: int = 30
    premium_tier_daily_question_limit: int = 100

    # SQS
    teacher_queue_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
