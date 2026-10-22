"""Manually maintained registry of supported cities.

The registry deliberately stays small and explicit. City ids are stable storage
keys and include both the country code and the city slug. Unknown, malformed, or
unsupported values resolve to ``None``; there are no aliases or fuzzy matches.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class City:
    id: str
    country_code: str
    slug: str
    name: str
    timezone: str


_PUBLISHED_CITIES = (
    City(
        id="lt/vilnius",
        country_code="lt",
        slug="vilnius",
        name="Vilnius",
        timezone="Europe/Vilnius",
    ),
)

CITY_REGISTRY: Mapping[str, City] = MappingProxyType(
    {city.id: city for city in _PUBLISHED_CITIES}
)


def list_cities(registry: Mapping[str, City] | None = None) -> tuple[City, ...]:
    """Return supported cities in deterministic country/slug order."""
    entries = (CITY_REGISTRY if registry is None else registry).values()
    return tuple(sorted(entries, key=lambda city: (city.country_code, city.slug, city.id)))


def normalize_city_id(
    value: Any,
    registry: Mapping[str, City] | None = None,
) -> str | None:
    """Normalize a candidate city id and accept only exact registry keys.

    Surrounding whitespace and case are normalized. Everything else, including
    non-string values such as JSON arrays or objects, resolves to ``None``.
    """
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower()
    if not candidate:
        return None
    entries = CITY_REGISTRY if registry is None else registry
    return candidate if candidate in entries else None


def resolve_city(
    value: Any,
    registry: Mapping[str, City] | None = None,
) -> City | None:
    """Resolve a candidate city id to its registry entry, or ``None``."""
    city_id = normalize_city_id(value, registry)
    if city_id is None:
        return None
    entries = CITY_REGISTRY if registry is None else registry
    return entries[city_id]
