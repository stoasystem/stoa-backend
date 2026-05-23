from fastapi import APIRouter

router = APIRouter()


@router.post("")
async def submit_question():
    pass


@router.get("/{question_id}")
async def get_question(question_id: str):
    pass


@router.post("/{question_id}/request-teacher")
async def request_teacher(question_id: str):
    pass


@router.post("/{question_id}/feedback")
async def submit_feedback(question_id: str):
    pass
