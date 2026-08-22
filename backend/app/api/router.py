from fastapi import APIRouter

from .auth import router as auth_router
from .boards import router as boards_router
from .cards import router as cards_router
from .connectors import router as connectors_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(boards_router)
api_router.include_router(cards_router)
api_router.include_router(connectors_router)


@api_router.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
