from fastapi import APIRouter

router = APIRouter()


@router.get("/{student_id}/summary")
async def get_summary(student_id: str):
    pass


@router.get("/{student_id}/questions")
async def list_questions(student_id: str):
    pass
