from fastapi import APIRouter, Depends

from nexus.api.dependencies import enforce_rate_limit

router = APIRouter(
    prefix="/rate-limit",
    tags=["rate-limit"],
)


@router.get(
    "/check",
    dependencies=[Depends(enforce_rate_limit)],
)
async def rate_limit_check() -> dict[str, str]:
    return {"status": "allowed"}
