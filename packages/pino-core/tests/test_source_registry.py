from pino_core.config import SourceConfig
from pino_core.models import Record
from pino_core.sources import SourceRegistry


class DummySource:
    name = "dummy"

    def fetch(self) -> list[Record]:
        return []


def test_source_registry_builds_registered_factory() -> None:
    registry = SourceRegistry()
    registry.register("dummy", lambda config: DummySource())

    sources = registry.build_many(
        [
            SourceConfig(name="first", type="dummy"),
            SourceConfig(name="second", type="dummy", enabled=False),
        ],
    )

    assert len(sources) == 1
    assert isinstance(sources[0], DummySource)

