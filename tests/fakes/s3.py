"""An S3 double for the upload flow: multipart state, presigned part PUTs, versions.

It keeps what S3 keeps for one bucket and makes the checks S3 makes on a presigned
part PUT (signed length and SHA-256), so a test can drive the real upload routes
end to end without the API ever seeing a part's bytes (#136).
"""

from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, urlparse


MIN_PART_BYTES = 5 * 1024 * 1024


def b64_sha256(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode("ascii")


class MultipartS3:
    """Multipart state, presigned PUTs and the checks S3 makes on them."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket
        self.uploads: dict[str, dict[str, Any]] = {}
        self.signed: dict[str, dict[str, Any]] = {}
        self.objects: dict[tuple[str, str], dict[str, Any]] = {}
        self.server_side_part_writes = 0
        self.completions_sent = 0

    # -- what the API calls ---------------------------------------------------------

    def create_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["Bucket"] == self.bucket and kwargs["ChecksumAlgorithm"] == "SHA256"
        upload_id = f"mp-{len(self.uploads) + 1}"
        self.uploads[upload_id] = {"Key": kwargs["Key"], "parts": {}}
        return {"UploadId": upload_id}

    def generate_presigned_url(self, ClientMethod: str, Params: dict[str, Any], ExpiresIn: int, HttpMethod: str) -> str:
        assert ClientMethod == "upload_part" and HttpMethod == "PUT" and ExpiresIn > 0
        token = f"sig-{len(self.signed) + 1}"
        self.signed[token] = dict(Params)
        return (
            f"https://{Params['Bucket']}.s3.test/{Params['Key']}"
            f"?uploadId={Params['UploadId']}&partNumber={Params['PartNumber']}&X-Amz-Signature={token}"
        )

    def upload_part(self, **kwargs: Any) -> dict[str, Any]:
        self.server_side_part_writes += 1
        raise AssertionError("part bytes must not pass through the API")

    def list_parts(self, **kwargs: Any) -> dict[str, Any]:
        parts = self.uploads[kwargs["UploadId"]]["parts"]
        return {
            "Parts": [
                {"PartNumber": number, **{k: v for k, v in part.items() if k != "data"}}
                for number, part in sorted(parts.items())
            ],
            "IsTruncated": False,
        }

    def complete_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self.completions_sent += 1
        upload = self.uploads.pop(kwargs["UploadId"])
        listed = kwargs["MultipartUpload"]["Parts"]
        data = b""
        for index, entry in enumerate(listed):
            part = upload["parts"][entry["PartNumber"]]
            assert entry["ETag"] == part["ETag"]
            assert entry["ChecksumSHA256"] == part["ChecksumSHA256"]
            if index < len(listed) - 1:
                assert part["Size"] >= MIN_PART_BYTES, "EntityTooSmall"
            data += part["data"]
        return self._store(kwargs["Key"], data, {"upload-id": "staging"})

    def abort_multipart_upload(self, **kwargs: Any) -> dict[str, Any]:
        self.uploads.pop(kwargs["UploadId"], None)
        return {}

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        stored = self.objects[(kwargs["Key"], kwargs["VersionId"])]
        return {"Body": BytesIO(stored["data"]), "ContentLength": len(stored["data"])}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        data = kwargs["Body"].read()
        assert len(data) == kwargs["ContentLength"]
        assert b64_sha256(data) == kwargs["ChecksumSHA256"]
        return self._store(kwargs["Key"], data, dict(kwargs["Metadata"]))

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        stored = self.objects[(kwargs["Key"], kwargs["VersionId"])]
        return {key: value for key, value in stored.items() if key != "data"}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.objects.pop((kwargs["Key"], kwargs.get("VersionId")), None)
        return {}

    def list_object_versions(self, **kwargs: Any) -> dict[str, Any]:
        return {
            "Versions": [
                {"Key": key, "VersionId": version, "ETag": stored["ETag"]}
                for (key, version), stored in self.objects.items()
                if key == kwargs.get("Prefix")
            ]
        }

    def _store(self, key: str, data: bytes, metadata: dict[str, str]) -> dict[str, Any]:
        version = f"v-{len(self.objects) + 1}"
        stored = {
            "data": data,
            "VersionId": version,
            "ETag": f'"{hashlib.md5(data).hexdigest()}"',
            "ContentLength": len(data),
            "ChecksumSHA256": b64_sha256(data),
            "Metadata": metadata,
        }
        self.objects[(key, version)] = stored
        return {"VersionId": version, "ETag": stored["ETag"], "ChecksumSHA256": stored["ChecksumSHA256"]}

    # -- what the browser does -----------------------------------------------------

    def browser_put(self, url: str, method: str, headers: dict[str, str], body: bytes) -> int:
        """A PUT on a presigned URL, refused the way S3 refuses a signature mismatch."""
        assert method == "PUT"
        token = parse_qs(urlparse(url).query)["X-Amz-Signature"][0]
        params = self.signed[token]
        if len(body) != params["ContentLength"]:
            return 403
        if headers.get("x-amz-checksum-sha256") != params["ChecksumSHA256"]:
            return 403
        if b64_sha256(body) != params["ChecksumSHA256"]:
            return 400  # BadDigest
        upload = self.uploads[params["UploadId"]]
        upload["parts"][params["PartNumber"]] = {
            "data": body,
            "Size": len(body),
            "ETag": f'"{hashlib.md5(body).hexdigest()}"',
            "ChecksumSHA256": params["ChecksumSHA256"],
        }
        return 200
