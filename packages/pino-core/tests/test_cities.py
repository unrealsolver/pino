from __future__ import annotations

from types import MappingProxyType

from pino_core.cities import City, list_cities, normalize_city_id, resolve_city


def test_published_registry_contains_only_vilnius() -> None:
    cities = list_cities()

    assert [(city.id, city.country_code, city.slug, city.name, city.timezone) for city in cities] == [
        ("lt/vilnius", "lt", "vilnius", "Vilnius", "Europe/Vilnius")
    ]


def test_city_ids_are_normalized_and_must_match_the_registry() -> None:
    assert normalize_city_id("  LT/Vilnius  ") == "lt/vilnius"
    assert normalize_city_id("lt/vilnius") == "lt/vilnius"
    assert normalize_city_id("vilnius") is None
    assert normalize_city_id("lt/kaunas") is None
    assert normalize_city_id("lt/vilnius/extra") is None


def test_non_string_and_empty_city_values_resolve_to_none() -> None:
    for value in (None, "", "   ", 42, True, ["lt/vilnius"], {"id": "lt/vilnius"}):
        assert normalize_city_id(value) is None


def test_fixture_registry_is_sorted_and_resolves_alternate_city() -> None:
    registry = MappingProxyType(
        {
            "fixture/foreign": City(
                id="fixture/foreign",
                country_code="zz",
                slug="foreign",
                name="Foreign",
                timezone="America/New_York",
            ),
            "lt/vilnius": City(
                id="lt/vilnius",
                country_code="lt",
                slug="vilnius",
                name="Vilnius",
                timezone="Europe/Vilnius",
            ),
        }
    )

    assert [city.id for city in list_cities(registry)] == ["lt/vilnius", "fixture/foreign"]
    assert normalize_city_id(" Fixture/Foreign ", registry) == "fixture/foreign"
    assert resolve_city("fixture/foreign", registry).timezone == "America/New_York"
    assert resolve_city("lt/kaunas", registry) is None
