from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from pino_core.config import PinoConfig
from pino_core.storage import DatabaseStore
from pino_web.repositories.events import EventRepository
from pino_web.services.events import EventService


def get_config(request: Request) -> PinoConfig:
    return request.app.state.config


def get_store(request: Request) -> DatabaseStore:
    return request.app.state.store


def get_event_repository(
    store: Annotated[DatabaseStore, Depends(get_store)],
) -> EventRepository:
    return EventRepository(store)


def get_event_service(
    config: Annotated[PinoConfig, Depends(get_config)],
    repository: Annotated[EventRepository, Depends(get_event_repository)],
) -> EventService:
    return EventService(config=config, repository=repository)
