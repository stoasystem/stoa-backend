from fastapi import APIRouter

router = APIRouter()


@router.post("/presign")
async def get_presigned_url():
    """Return an S3 presigned PUT URL for direct client upload."""
    pass
