from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pino_core.stats import build_source_stats_report
from pino_core.storage import DatabaseStore

from pino_web.deps import get_store
from pino_web.schemas import StatsResponse

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def get_stats(
    store: Annotated[DatabaseStore, Depends(get_store)],
    weeks: int = Query(
        default=8,
        ge=1,
        le=52,
        description="Number of Monday-start ingestion weeks to report.",
    ),
) -> StatsResponse:
    report = build_source_stats_report(store, weeks=weeks)
    return StatsResponse.model_validate(report.model_dump())
