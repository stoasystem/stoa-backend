from fastapi import APIRouter

router = APIRouter()


@router.get("/queue")
async def get_queue():
    pass


@router.post("/questions/{question_id}/takeover")
async def takeover(question_id: str):
    pass


@router.post("/questions/{question_id}/reply")
async def reply(question_id: str):
    pass


@router.put("/questions/{question_id}/resolve")
async def resolve(question_id: str):
    pass
