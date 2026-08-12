from __future__ import annotations

from fastapi import APIRouter

from pino_web.routes.events import router as events_router

router = APIRouter()
router.include_router(events_router)
