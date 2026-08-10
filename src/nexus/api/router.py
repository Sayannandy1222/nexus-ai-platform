from fastapi import APIRouter

from nexus.api.routes.generate import router as generate_router
from nexus.api.routes.health import router as health_router
from nexus.api.routes.metrics import router as metrics_router
from nexus.api.routes.rate_limit import router as rate_limit_router

api_router = APIRouter(
    prefix="/v1",
)

api_router.include_router(generate_router)
api_router.include_router(health_router)
api_router.include_router(metrics_router)
api_router.include_router(rate_limit_router)
