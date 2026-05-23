from fastapi import APIRouter

router = APIRouter()


@router.get("/{parent_id}/children")
async def list_children(parent_id: str):
    pass


@router.get("/{parent_id}/reports/{week}")
async def get_report(parent_id: str, week: str):
    pass
