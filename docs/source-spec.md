# Source Adapter Spec

This document is for humans or coding agents adding a new Pino source inside this repository. The MVP integration point is the repo itself, not an external plugin system.

The record shape below is intentionally raw. Normalized query fields belong to
the reusable refinement layer documented in [refinements.md](refinements.md).

## Goal

A source adapter fetches one configured source and returns generic `Record` objects. Once registered, the existing commands can use it:

- `pino check` fetches and stores records.
- `pino refine` extracts reusable normalized items from unrefined records.
- `pino digest` summarizes relevant records.
- `pino chat` can retrieve records through tools.

Keep source code source-specific. Keep refinement, ranking, digest, memory, and chat logic in `pino-core`.

## Least Ugly Repo-Local Path

1. Add a module under `packages/pino-integration/src/pino_integration/`, for example `my_events.py`.
2. Implement a class with `name: str` and `fetch(self) -> list[Record]`.
3. Implement a factory `build_my_events_source(config: SourceConfig) -> SourceAdapter`.
4. Register the factory in `packages/pino-integration/src/pino_integration/registry.py`.
5. Add one source config entry in `config.yaml` or `config.local.yaml`.
6. Add parser tests with local fixtures before relying on live fetches.

This keeps custom integrations visible and easy to modify while avoiding premature plugin packaging.

## Adapter Contract

Every adapter must satisfy `pino_core.sources.SourceAdapter`:

```python
class SourceAdapter(Protocol):
    name: str

    def fetch(self) -> list[Record]:
        """Fetch records from a source."""
```

Adapters should be deterministic for the same source contents. Network code belongs in `fetch`; HTML/JSON parsing should live in separate functions so tests can use fixtures without network.

Sources that support incremental reads can additionally satisfy `CursorSourceAdapter`:

```python
class CursorSourceAdapter(Protocol):
    name: str

    def fetch_since(self, cursor: str | None) -> CursorFetchResult:
        """Fetch records newer than a durable source cursor."""
```

The check pipeline stores cursors in SQLite by configured source name and calls
`fetch_since` when available. Return the next cursor only after the returned
batch represents a complete incremental read. The pipeline advances it after
all returned records have been stored successfully.

## Record Shape

Return `pino_core.models.Record` objects. For event-like records, prefer a
compact raw capture shape:

```python
Record(
    kind="event",
    source=source_name,
    external_id=stable_source_id,
    title=title,
    text="Title. Category: ... Location: ... Time: ...",
    url=url,
    payload={
        "category": category,
        "location": location,
        "display_time": display_time,
        "image_url": image_url,
        "raw": raw_source_data,
    },
    provenance={
        "adapter": "my_events",
        "page_url": page_url,
        "index": index,
    },
)
```

Required fields are `kind`, `source`, and `text`; useful records should also
include stable identity, title, URL, source-native payload values, and
provenance when available.

## Field Rules

- `kind`: generic type such as `event`, `telegram_message`, `article`, or `note`.
- `source`: configured source name, not just adapter type.
- `external_id`: stable ID from the source when available. Use URL slug, message ID, event ID, or canonical URL-derived ID.
- `title`: short display title when available.
- `text`: compact human-readable source summary. This is used by refinement, so include the important facts.
- `url`: canonical URL for the item when available.
- `payload`: source-native metadata useful for audit, debug, or later reprocessing. Keep wrapper keys in English.
- `provenance`: parser/debug context, including adapter name and source location.

Do not normalize query dates, taxonomy categories, or inferred locations inside
adapters. The refinement layer owns those fields.

### Optional Location Scopes

`payload.location` remains the human-facing venue, address, or source label. When the source item also provides trustworthy geographic specificity, adapters may add optional machine-readable `payload.location_scopes`.

```python
payload={
    "location": "MO muziejus",
    "location_scopes": ["LT/vilnius"],
}
```

Use an array because one item may apply to several places:

```python
"location_scopes": ["LT/vilnius", "LT/kaunas"]
```

Use an ISO 3166-1 alpha-2 country code plus a lowercase ASCII city/region slug. Use `*` only when the source item explicitly applies country-wide:

```python
"location_scopes": ["LT/*"]
```

Rules:

- `location_scopes` is optional. Omit it or use an empty list when the source does not provide enough evidence.
- Do not infer `LT/vilnius` merely because Pino usually targets Vilnius.
- Do not treat a missing or empty scope as `LT/*`.
- Preserve the source evidence in provenance when useful, for example `"location_scope_source": "listing_page"`.
- Keep this in payload for now. Do not promote scopes to required top-level `Record` fields.

## Factory Shape

Use `SourceConfig` fields consistently:

- `config.name`: user-facing source name to store in records.
- `config.url`: listing page, feed URL, API endpoint, or channel URL.
- `config.path`: local fixture/file path for file-backed sources.
- `config.settings`: source-specific options such as CSS selectors, limits, or resolved credentials.

Secrets must be referenced explicitly in YAML as `env:NAME`; config loading resolves those strings from the process environment or `.env` before source factories receive `SourceConfig`.

Example:

```python
from pino_core.config import SourceConfig
from pino_core.sources import SourceAdapter


def build_my_events_source(config: SourceConfig) -> SourceAdapter:
    if config.url is None:
        raise ValueError("my_events source requires url")
    return MyEventsSource(
        url=config.url,
        name=config.name,
        limit=int(config.settings.get("limit", 50)),
    )
```

Register it in `pino_integration.registry`:

```python
from pino_integration.my_events import build_my_events_source


def register_integrations(registry: SourceRegistry) -> SourceRegistry:
    registry.register("my_events", build_my_events_source)
    return registry
```

Then configure it:

```yaml
sources:
  - name: my-events
    type: my_events
    url: https://example.test/events
    enabled: true
    settings:
      limit: 50
```

## Parser Guidelines

- Prefer source-provided structured data such as JSON-LD, meta tags, API JSON, or embedded data blobs before fragile CSS scraping.
- Keep live HTTP requests small: set timeout, User-Agent, and reasonable limits.
- Do not make one adapter crawl a whole website. Fetch the configured listing/feed/channel and, only when justified, specific detail pages linked from that listing.
- Preserve useful raw source fragments in `payload.raw` when they help debug parser mistakes.
- Tolerate empty pages and missing optional fields.
- Deduplicate within the source by returning stable `external_id` and URL-derived identity where possible.

## Test Checklist

Add focused tests under `packages/pino-integration/tests/`:

- Parser fixture test for one representative item.
- Missing optional fields test if the source is messy.
- Source-native date/time payload assertion when the source exposes date fields.
- URL normalization assertion for relative links.
- Factory validation test if required config is non-obvious.

Live network tests should not be required for the normal test suite.

## Coding Agent Prompt

When asking a coding agent to add a source, include:

```text
Add a Pino source adapter named <type_name> for <source URL/channel>.
Follow docs/source-spec.md.
Keep parsing in packages/pino-integration/src/pino_integration/<type_name>.py.
Register it in pino_integration.registry.
Add fixture-based tests under packages/pino-integration/tests/.
Return generic raw Record objects with title, text, url, source-native payload values, optional source-derived location_scopes, and provenance.
Do not add broad plugin architecture.
```

## When To Abstract Further

Do not add an external plugin system until repo-local adapters become painful. Signs it is time:

- Friends need private integrations outside the repo.
- Source adapters require optional dependencies that should not install by default.
- There are multiple independently maintained integration packs.
- Registration conflicts or config schema drift become common.

Until then, one source module plus one registry line is the intended extension point.
