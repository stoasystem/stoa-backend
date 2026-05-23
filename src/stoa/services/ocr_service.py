"""Amazon Rekognition — extract text from homework images."""
import boto3
from stoa.config import settings


def extract_text_from_s3(bucket: str, key: str) -> str:
    """Use Rekognition DetectText to extract text from an S3 image."""
    client = boto3.client("rekognition", region_name=settings.aws_region)
    response = client.detect_text(Image={"S3Object": {"Bucket": bucket, "Name": key}})
    detections = sorted(
        [d for d in response["TextDetections"] if d["Type"] == "LINE"],
        key=lambda x: x["Geometry"]["BoundingBox"]["Top"],
    )
    return "\n".join(d["DetectedText"] for d in detections)
