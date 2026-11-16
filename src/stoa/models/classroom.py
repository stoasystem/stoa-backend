"""What entering a help request's classroom returns (#467)."""

from pydantic import BaseModel

from stoa.services.classroom import ClassroomCredentials


class ClassroomVoice(BaseModel):
    roomUrl: str
    token: str


class ClassroomEntry(BaseModel):
    """The caller's whiteboard address and voice credentials, valid until `expiresAt`."""

    whiteboardUrl: str
    voice: ClassroomVoice
    expiresAt: str

    @classmethod
    def of(cls, credentials: ClassroomCredentials) -> "ClassroomEntry":
        return cls(
            whiteboardUrl=credentials.whiteboard_url,
            voice=ClassroomVoice(
                roomUrl=credentials.voice_room_url, token=credentials.voice_token
            ),
            expiresAt=credentials.expires_at.isoformat(),
        )
