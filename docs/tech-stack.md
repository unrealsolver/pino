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
- Rich for readable terminal output

Do not start with PostgreSQL, Qdrant, Docker Compose, or LangGraph unless the first useful workflows clearly need them.

## Package Structure

Use a `uv` workspace if the repository is split into a small number of coarse packages. The value is one shared lockfile, consistent dependency resolution, and clean separation between core logic and runnable apps.

Suggested starting shape:

- `packages/pino-core`: generic records/artifacts, pipeline, memory abstractions, evaluation logic, provider interfaces.
- `apps/pino-cli`: Typer CLI that calls `pino-core`.
- `apps/pino-daemon`: future daemon process that calls the same `pino-core`.
- `packages/pino-integrations`: optional later package if integrations become large enough to separate.

Current scaffold starts with `packages/pino-core` and `apps/pino-cli`. The daemon package should be added after the batch workflow has enough real behavior to keep resident.

Do not create one package per integration or per domain entity at the start. Keep most code inside `pino-core` until the boundaries prove they deserve separate packages.

The root should own workspace-level settings, shared tooling, and the lockfile. Individual packages should own only their package metadata and direct dependencies.

## Runtime Shape

Pino should eventually run as a daemon.

For the MVP, the core workflow can still be exposed as explicit CLI commands because that makes development, debugging, and testing simpler:

- `pino check`
- `pino digest`
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
- Good enough for generic records, generated artifacts, chat history, and active memory.
- Can support simple full-text search.
- Leaves a clear migration path to PostgreSQL if needed.

Avoid making the storage schema mirror the first event-ingestion pipeline too closely. Source-specific concepts should live in source adapters or typed payloads, not in top-level storage tables.

Better first-level storage concepts:

- `records`: generic captured or derived facts/items with type, source, timestamps, payload, and provenance.
- `artifacts`: generated outputs such as digests, reports, summaries, or exports.
- `chat_messages`: durable conversation history.
- `active_memory`: explicit long-lived facts and preferences.
- `tasks`: optional later, for daemon-managed recurring or interrupting work.

Event candidates, dedup groups, ranking results, and source run details can be represented as record/artifact types until the system proves that they need dedicated tables.

Postpone vector storage. Add embeddings and Qdrant only after there is a concrete semantic-memory use case that SQLite search cannot cover.

## LLM Layer

Use one internal provider interface and keep provider-specific details out of core logic.

Providers:

- Infercom as the primary remote provider.
- Ollama as the local fallback and integration-test provider.

The application should still be partly useful without LLM calls. Fetching, storing, listing, simple filtering, and deterministic tests should not require a remote model.

## Interactive Agent Shape

Pino should use an LLM-to-tools design, not a kitchen-sink autonomous agent.

The interactive path should look like this:

1. Accept a natural-language user request.
2. Store the user message.
3. Assemble recent chat history, active memory, and available tool descriptions.
4. Ask the configured LLM for either a normal response or a bounded tool request.
5. Execute only explicit local tools.
6. Store tool results and the assistant response.

Initial tools should be narrow and inspectable:

- `memory.add`
- `memory.list`
- `records.list`
- `digest.create`
- `sources.check`

Do not expose shell execution, arbitrary filesystem access, browser automation, or generic Python execution to the LLM. Add real-world tools one at a time after the bounded local loop works.

`pino chat` is part of the product direction because Pino should handle user requests through a natural-language interface. It is also the first practical proof of Infercom and Ollama provider integration.

## Integrations

Each source should be isolated behind a small interface. Integrations should fetch and parse source-specific data, then return generic records with payloads and provenance. Evaluation and digest decisions belong in the core.

Initial libraries:

- Telethon for Telegram.
- httpx for websites.
- BeautifulSoup or selectolax for HTML parsing.
- dateparser or explicit parser helpers for dates.

Avoid browser automation until a source requires it.

## Core Pipeline

Keep the first pipeline batch-oriented and explicit:

1. Fetch configured sources.
2. Store captured records with provenance.
3. Normalize or enrich records where useful.
4. Relate, merge, or suppress duplicates.
5. Evaluate records against current goals.
6. Generate concise artifacts such as digests.
7. Store and print/output the digest.

This pipeline should be callable from both CLI commands and the future daemon.

## Project Layout

Suggested internal layout for `pino-core`:

- `pino/config`
- `pino/core`
- `pino/integrations`
- `pino/providers`
- `pino/storage`
- `tests`

Important core concepts:

- `Record`
- `Artifact`
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
