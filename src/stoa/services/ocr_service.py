"""Private OCR boundary for owner-resolved homework image attachments."""
from dataclasses import dataclass

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from stoa.config import settings


_TRANSIENT_CODES = {
    "InternalServerError",
    "ProvisionedThroughputExceededException",
    "RequestTimeout",
    "ServiceUnavailableException",
    "ThrottlingException",
}
_TERMINAL_OBJECT_CODES = {
    "InvalidImageFormatException",
    "InvalidS3ObjectException",
    "ResourceNotFoundException",
}


@dataclass(frozen=True, slots=True)
class OcrAttachmentFailure(Exception):
    category: str
    terminal: bool


def extract_text_from_attachment(
    attachment: dict,
    *,
    settings_obj=settings,
    client=None,
) -> str:
    """OCR one internal attachment; storage coordinates never cross the service API."""
    if (
        attachment.get("status") != "active"
        or attachment.get("detected_type") not in {"image/jpeg", "image/png"}
        or not attachment.get("object_key")
    ):
        raise OcrAttachmentFailure("invalid_attachment", terminal=True)
    rekognition = client or boto3.client(
        "rekognition", region_name=settings_obj.aws_region
    )
    try:
        response = rekognition.detect_text(
            Image={
                "S3Object": {
                    "Bucket": settings_obj.s3_images_bucket,
                    "Name": attachment["object_key"],
                }
            }
        )
        detections = sorted(
            [
                value
                for value in response.get("TextDetections", [])
                if value.get("Type") == "LINE"
            ],
            key=lambda value: value["Geometry"]["BoundingBox"]["Top"],
        )
        return "\n".join(str(value["DetectedText"]) for value in detections)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code") or "")
        if code in _TERMINAL_OBJECT_CODES:
            raise OcrAttachmentFailure("invalid_object", terminal=True) from None
        if code in _TRANSIENT_CODES:
            raise OcrAttachmentFailure("service_unavailable", terminal=False) from None
        raise OcrAttachmentFailure("service_unavailable", terminal=False) from None
    except BotoCoreError:
        raise OcrAttachmentFailure("service_unavailable", terminal=False) from None
    except (KeyError, TypeError, ValueError):
        raise OcrAttachmentFailure("invalid_provider_response", terminal=True) from None
