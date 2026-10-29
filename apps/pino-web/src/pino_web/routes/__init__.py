from __future__ import annotations

from fastapi import APIRouter

from pino_web.routes.cities import router as cities_router
from pino_web.routes.events import router as events_router
from pino_web.routes.stats import router as stats_router

router = APIRouter()
router.include_router(cities_router)
router.include_router(events_router)
router.include_router(stats_router)
