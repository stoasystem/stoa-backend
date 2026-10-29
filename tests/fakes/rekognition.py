"""A Rekognition double for image moderation (#138).

`detect_moderation_labels` answers with the labels it was given, or fails with the
error it was given. Like the service it drops labels under `MinConfidence`
(default 50), so a test cannot pass only because its labels were never filtered.
With no labels it passes every image, which is what a test about something other
than moderation needs to complete an image upload.
"""

from __future__ import annotations

from typing import Any


class FakeRekognition:
    def __init__(self, labels: list[dict[str, Any]] | None = None) -> None:
        self.labels = labels or []
        self.model_version = "7.0"
        self.error: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    def detect_moderation_labels(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        floor = kwargs.get("MinConfidence", 50.0)
        return {
            "ModerationLabels": [label for label in self.labels if label["Confidence"] >= floor],
            "ModerationModelVersion": self.model_version,
            "ContentTypes": [],
        }
