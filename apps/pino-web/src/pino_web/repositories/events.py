from __future__ import annotations

from datetime import datetime

from pino_core.storage import DatabaseStore, EventQueryResult


class EventRepository:
    def __init__(self, store: DatabaseStore) -> None:
        self.store = store

    def query_events(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        categories: list[str],
        min_score: float,
        text_query: str,
        limit: int,
    ) -> list[EventQueryResult]:
        return self.store.query_events(
            window_start=window_start,
            window_end=window_end,
            categories=categories,
            min_score=min_score,
            text_query=text_query,
            limit=limit,
        )
