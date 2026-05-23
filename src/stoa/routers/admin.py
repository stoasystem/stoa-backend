from fastapi import APIRouter

router = APIRouter()


@router.get("/users")
async def list_users():
    pass


@router.patch("/users/{user_id}")
async def update_user(user_id: str):
    pass


@router.get("/stats")
async def get_stats():
    pass
