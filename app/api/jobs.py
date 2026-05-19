from fastapi import APIRouter

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/health")
async def health():
    return {"status": "ok"}
