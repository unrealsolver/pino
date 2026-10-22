from __future__ import annotations

from fastapi import APIRouter

from pino_core.cities import list_cities
from pino_web.schemas import CityItem, CityListResponse

router = APIRouter(prefix="/api", tags=["cities"])


@router.get("/cities", response_model=CityListResponse)
def list_supported_cities() -> CityListResponse:
    return CityListResponse(
        cities=[
            CityItem(
                id=city.id,
                country_code=city.country_code,
                slug=city.slug,
                name=city.name,
                timezone=city.timezone,
            )
            for city in list_cities()
        ]
    )
