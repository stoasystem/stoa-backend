"""DynamoDB single-table client wrapper."""
import boto3
from functools import lru_cache
from stoa.config import settings


@lru_cache
def get_table():
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(settings.dynamodb_table_name)
