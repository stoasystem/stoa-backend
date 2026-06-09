from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_REPORTS_BUCKET_PLACEHOLDER = "stoa-reports"
PRODUCTION_ENVIRONMENTS = {"production", "prod"}


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
    s3_reports_bucket: str = LOCAL_REPORTS_BUCKET_PLACEHOLDER
    s3_presign_expiry_seconds: int = 300
    immutable_audit_storage_mode: str = "disabled"
    immutable_audit_storage_cdk_managed: bool = False
    immutable_audit_storage_resource: str = ""
    immutable_audit_storage_prefix: str = ""

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

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in PRODUCTION_ENVIRONMENTS

    @property
    def report_artifacts_bucket(self) -> str:
        bucket = self.s3_reports_bucket.strip()
        if self.is_production and (
            not bucket or bucket == LOCAL_REPORTS_BUCKET_PLACEHOLDER
        ):
            raise ValueError(
                "S3_REPORTS_BUCKET must be configured by CDK in production"
            )
        return bucket or LOCAL_REPORTS_BUCKET_PLACEHOLDER

    # Bedrock
    # EU cross-region inference profile — no manual model access approval needed
    bedrock_model_id: str = "eu.anthropic.claude-sonnet-4-6"
    bedrock_max_tokens: int = 2048

    # Limits (per role per day)
    free_tier_daily_question_limit: int = 5
    standard_tier_daily_question_limit: int = 30
    premium_tier_daily_question_limit: int = 100

    # Conversation message limits per day (all tiers share one generous limit;
    # chat is the core UX — don't over-restrict)
    daily_chat_message_limit: int = 80

    # Practice hint limits per day
    daily_hint_limit: int = 30

    # SQS
    teacher_queue_url: str = ""

    # Lambda targets
    weekly_report_function_name: str = "stoa-weekly-report"

    # WebSocket realtime notifications
    websocket_api_endpoint: str = ""
    websocket_connection_ttl_seconds: int = 600


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
