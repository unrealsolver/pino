# Tech Stack

This document records the current stack direction for Pino. It is expected to change as the project becomes more concrete.

## Current Recommendation

Use a small Python stack with inspectable local storage and explicit module boundaries. A `uv` workspace is reasonable, but it should be used for coarse deployable/library boundaries rather than for every internal concept.

- Python 3.12+
- `uv` workspace for dependency and environment management
- Typer for CLI commands
- Pydantic for config and domain models
- YAML for editable local configuration
- SQLite as the first storage backend
- SQLAlchemy or SQLModel for persistence
- pytest for tests
- prek for Git hook management
- Rich for readable terminal output

Do not start with PostgreSQL, Qdrant, Docker Compose, or LangGraph unless the first useful workflows clearly need them.

## Package Structure

Use a `uv` workspace if the repository is split into a small number of coarse packages. The value is one shared lockfile, consistent dependency resolution, and clean separation between core logic and runnable apps.

Suggested starting shape:

- `packages/pino-core`: generic records, pipeline, memory abstractions, evaluation logic, provider interfaces.
- `packages/pino-llm`: unified LLM interface, provider adapters, request/response normalization, and provider error wrapping.
- `packages/pino-integration`: third-party source adapters and their parser dependencies.
- `apps/pino-cli`: Typer CLI that calls `pino-core`.
- `apps/pino-daemon`: future daemon process that calls the same `pino-core`.

Current scaffold starts with `packages/pino-core`, `packages/pino-integration`, `packages/pino-llm`, and `apps/pino-cli`. The daemon package should be added after the batch workflow has enough real behavior to keep resident.

Do not create one package per integration or per domain entity at the start. Keep third-party integration code in `pino-integration` and generic records, storage, pipeline, and evaluation code in `pino-core`.

The root should own workspace-level settings, shared tooling, and the lockfile. Individual packages should own only their package metadata and direct dependencies.

## Runtime Shape

Pino should eventually run as a daemon.

For the MVP, the core workflow can still be exposed as explicit CLI commands because that makes development, debugging, and testing simpler:

- `pino check`
- `pino digest`: create a relevance-windowed digest, defaulting to current/upcoming records in the next 14 days.
- `pino memory add`
- `pino memory list`
- `pino sources list`

The daemon should come after the batch workflow is reliable. It can reuse the same core services and add long-running scheduling, interrupt rules, and notification behavior.

Reasonable progression:

1. Build batch commands.
2. Run batch commands manually or from `systemd` timers.
3. Add a daemon process once scheduling and interrupt behavior are worth keeping resident.

## Storage

Start with SQLite.

Reasons:

- Local-only.
- Easy to inspect and back up.
- Good enough for generic records, evaluations, chat history, and active memory.
- Can support simple full-text search.
- Leaves a clear migration path to PostgreSQL if needed.

Avoid making the storage schema mirror the first event-ingestion pipeline too closely. Source-specific concepts should live in source adapters or typed payloads, not in top-level storage tables.

Better first-level storage concepts:

- `records`: generic captured or derived facts/items with type, source, timestamps, payload, and provenance.
- `chat_messages`: durable conversation history.
- `active_memory`: explicit long-lived facts and preferences.
- `tasks`: optional later, for daemon-managed recurring or interrupting work.

Event candidates, dedup groups, ranking results, and source run details can be represented as record payloads or evaluation data until the system proves that they need dedicated tables.

### Record Normalization

Keep the first storage model generic, but do not leave every source adapter to invent incompatible metadata shapes.

Canonical record metadata should use English keys and stable machine-readable values. Source-native labels and text should remain available for inspection, but they should not be the only copy of critical fields used by evaluation, sorting, or digest generation.

Recommended normalized fields for event-like records:

- `payload.start_at_utc`: ISO 8601 UTC event start datetime.
- `payload.end_at_utc`: ISO 8601 UTC event end datetime when known.
- `payload.timezone`: source/event timezone used during normalization, usually `Europe/Vilnius`.
- `payload.display_time`: source display text for humans/debugging.
- `payload.category` and `payload.categories`: English canonical labels when available from the source.
- `payload.location`: venue/location name in the most useful available language.
- `payload.raw`: source-native values that were transformed or could be useful for debugging.

Generic record timing should distinguish:

- `captured_at`: when Pino ingested/stored the record.
- `relevant_from` and `relevant_to`: the generic query window for when the record is useful to query or act on, for example "events relevant this week".
- event/source-specific time details: exact start/end/publication metadata in payload.

Point-like records may use the same timestamp for `relevant_from` and `relevant_to`. Range-like records should fill both sides when known. Event start/end should remain paired in payload as source-specific exact details, while the top-level relevance window remains generic.

For Vilnius event sources that publish date/time without a timezone, interpret the source time as `Europe/Vilnius` before converting to UTC. Do not store naive datetimes as canonical fields.

If a source provides only Lithuanian labels for critical metadata, store those labels in `payload.raw` and either keep the canonical field unset or fill it through an explicit normalization/enrichment function. Avoid silent best-effort translations inside ad hoc parser code.

Record idempotency is a deterministic storage concern, not an LLM or vector-search concern. `Record` may carry optional identity hints, and storage enforces a unique fingerprint:

1. Prefer `source + kind + external_id` when an integration provides `external_id`.
2. Else use `source + kind + normalized_url` when a URL exists.
3. Else use `source + kind + normalized_title + normalized_text`.

This prevents repeated source checks from creating duplicate rows. Semantic duplicate detection across different sources can be added later as an evaluation/enrichment step if needed.

Postpone vector storage. Add embeddings and Qdrant only after there is a concrete semantic-memory use case that SQLite search cannot cover.

## LLM Layer

Use `pino-llm` as the single internal provider interface and keep provider-specific details out of core logic.

Providers:

- Infercom as the primary remote provider.
- Ollama as the local fallback and integration-test provider.

The package should wrap request/response quirks and normalize provider errors. For example, providers that do not support raw `tool` role history should receive tool results as ordinary context rather than OpenAI tool-call protocol messages.

The package also owns the simple JSON action protocol used by `pino chat`: model responses are parsed as either final text or a bounded tool request. Invalid JSON falls back to final text, and unavailable tools are handled by the chat layer instead of crashing.

The application should still be partly useful without LLM calls. Fetching, storing, listing, simple filtering, and deterministic tests should not require a remote model.

Record evaluation is LLM-assisted rather than keyword-only. Deterministic code controls batching, config, persistence, retries, and caching; the configured model performs multilingual semantic classification against explicit goals. The default evaluation model alias is `simple`, which resolves to Infercom `gpt-oss-120b` in the current config.

## Interactive Agent Shape

Pino should use an LLM-to-tools design, not a kitchen-sink autonomous agent.

The interactive path should look like this:

1. Accept a natural-language user request.
2. Store the user message.
3. Assemble recent chat history, current local time, configured goals, active memory, and available tool descriptions.
4. Ask the configured LLM for either a normal response or a bounded tool request.
5. Execute only explicit local tools.
6. Store tool results and the assistant response.

Initial tools should be narrow and inspectable:

- `memory.add`
- `memory.list`
- `records.relevant`: preferred retrieval path for event/recommendation questions. It should query relevance-windowed records joined with evaluations and return title, source, score, goal matches, local time window, location, URL, and evaluation summary with raw text fallback. V1 arguments: `limit`, `days`, `min_score`, and `goals`.
- `records.list`: raw recent record inspection/debug only.
- `digest.create`
- `sources.check`

Do not add targeted `records.get` in v1. `records.relevant` should return enough detail for normal conversational recommendations; add lookup-by-id later only if follow-up questions need deeper record payloads.

Do not expose shell execution, arbitrary filesystem access, browser automation, or generic Python execution to the LLM. Add real-world tools one at a time after the bounded local loop works.

`pino chat` is part of the product direction because Pino should handle user requests through a natural-language interface. It is also the first practical proof of Infercom and Ollama provider integration.

Operational controls should include debug output, per-request history limits, visible recent chat history in interactive mode, and chat history reset so provider behavior can be inspected without manually editing the database.

Chat language should be session-consistent. Infer the response language from the user's current session unless the user explicitly asks for another language. This especially matters for generated relative date wording: use `Tuesday`, `today`, and `tomorrow` in English sessions, and Lithuanian equivalents such as `antradienį` in Lithuanian sessions. Date reasoning should use the configured local timezone and convert stored UTC event times only at the final presentation layer.

## Integrations

Each source should be isolated behind a small interface. Integrations should fetch and parse source-specific data, then return generic records with payloads and provenance. Evaluation and digest decisions belong in the core.

Source construction should use registered factories rather than a central `if/elif` chain. The registry owns source type resolution, and integrations provide small factory functions that build their adapters from config.

Initial libraries:

- Telethon for Telegram.
- httpx for websites.
- BeautifulSoup or selectolax for HTML parsing.
- dateparser or explicit parser helpers for dates.

Avoid browser automation until a source requires it.

Current source types:

- `kaveikti`: parses kaveikti.lt listing cards into generic `event` records with category, location, display time, start/end metadata, URL, and source-provided event-time ID when present.
- `telegram_channel`: fetches recent Telegram channel messages into generic `telegram_message` records with message identity, post URL, posted time, and engagement metadata when available.
- `vilnius_events`: parses vilnius-events.lt listing cards into generic `event` records with category, location, display time, URL slug identity, image URL, and listing provenance.

## Core Pipeline

Keep the first pipeline batch-oriented and explicit:

1. Fetch configured sources.
2. Store captured records with provenance.
3. Normalize or enrich records where useful.
4. Relate, merge, or suppress duplicates.
5. Evaluate records against current goals with cached structured evaluations.
6. Serve evaluated, relevance-windowed records to chat through `records.relevant`.
7. Generate and print/output concise digests.

This pipeline should be callable from both CLI commands and the future daemon.

## Project Layout

Suggested internal layout for `pino-core`:

- `pino/config`
- `pino/core`
- `pino/providers`
- `pino/storage`
- `tests`

Important core concepts:

- `Record`
- `SourceAdapter`
- `MemoryEntry`
- `ChatMessage`
- `Task`
- `Evaluation`

Avoid promoting use-case-specific concepts, such as event candidates or dedup groups, into first-class interfaces until the code repeatedly needs them.

## Deferred Choices

These are intentionally not first-step dependencies:

- LangGraph: consider only if orchestration becomes complex enough to justify it.
- PostgreSQL: consider if SQLite becomes limiting.
- Qdrant or another vector DB: consider after semantic search is proven necessary.
- Docker Compose: consider when there are multiple long-running services.
- Web/admin UI: consider after CLI workflows are useful.
