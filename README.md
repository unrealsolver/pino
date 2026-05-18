# Pino

Pino is a local-only personal agentic assistant for Ruslan. Her job is to monitor selected text sources, remember useful context, and surface only the information that is worth acting on.

This project is intentionally not a general-purpose assistant. The first useful version should be a small, inspectable system that can run scheduled checks and produce concise digests.

## Product Intent

Pino should help with emotionally or intellectually draining recurring tasks, especially discovering relevant events and occasions in Vilnius.

Current goals:

- Find places and occasions to meet women, including indirect options such as volunteering, social gatherings, and community events.
- Find metal music events.
- Find electronic music events, especially Open Synth Jam-like events where Ruslan can participate.
- Check selected internet sources daily and report actionable matches.
- Deduplicate events that appear in multiple sources.
- Keep persistent memory that can be reviewed and used by the agent on demand.

Non-goals:

- Do-anything autonomous agent.
- Image generation or image understanding.
- Generic question answering.
- Being broadly pleasant or chatty for its own sake.

## User Context

Pino's runtime persona:

- Name: Pino.
- Address the user as: Boss.
- User name: Ruslan.
- Age: 33.
- Background: migrant from Belarus living in Vilnius, Lithuania.
- Neighborhood: Naujamiestis.
- Lithuanian level: around A2.
- Work: senior-level software engineer.
- Hobbies: synths; metal guitar as a secondary hobby.
- Assumption: the user can handle technical detail and technical problems.

## MVP Scope

The first coherent version should do the following:

1. Load configuration from local YAML files.
2. Read from a small set of configured sources.
3. Normalize discovered items into a shared event/item model.
4. Deduplicate similar events.
5. Rank items against the current goals.
6. Produce a concise CLI digest.
7. Store raw observations, processed items, chat history, and active memory in persistent local storage.
8. Support Infercom as the primary LLM provider and Ollama as a local fallback/test provider.

The MVP does not need a web admin panel, Logseq integration, or a large autonomy framework. Those can be added after the ingestion, memory, and digest loop is useful.

## Architecture Direction

Keep the app split into an abstract core and replaceable interfaces.

Suggested boundaries:

- `core`: scheduling-independent business logic, item models, memory APIs, ranking, deduplication, digest generation.
- `providers`: LLM provider adapters, currently Infercom and Ollama.
- `integrations`: one isolated module per external source.
- `storage`: persistent memory and event/item storage.
- `cli`: user-facing commands for running checks, viewing digests, and inspecting memory.
- `config`: typed configuration loading and validation.

Prefer small explicit interfaces over a large autonomous-agent abstraction. LangGraph may be used if it clearly simplifies orchestration, but it is not required for the MVP.

## Tech Stack

- Python.
- `uv` for dependency and environment management.
- Local Linux deployment.
- Optional later: LangGraph, PostgreSQL, Qdrant, Docker Compose.

See [docs/tech-stack.md](docs/tech-stack.md) for the current stack direction and runtime design notes.

Target machine:

- Fedora Linux.
- AMD GPU with 16 GB VRAM.
- 64 GB RAM.
- 16-core / 32-thread CPU.

## LLM Providers

### Infercom

Infercom is the primary provider.

Default models:

- Smart/default model: `MiniMax-M2.5`.
- Simpler tasks: `gpt-oss-120b`.

Example client usage:

```python
from sambanova import SambaNova

client = SambaNova(
    api_key="<YOUR API KEY>",
    base_url="https://api.infercom.ai/v1",
)

response = client.chat.completions.create(
    model="DeepSeek-V3.1",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello!"},
    ],
    temperature=0.1,
    top_p=0.1,
)

print(response.choices[0].message.content)
```

The API key is stored locally in `INFERCOM_API_KEY`.

### Ollama

Ollama is the local fallback provider and integration-test provider.

Default model:

- `gpt-oss-20b`.

## Integrations

Each integration should be isolated behind a small source interface. Integrations should return structured observations/items rather than directly deciding digest output.

Initial sources:

- Telegram public channels:
  - `t.me/afishavilnius`
  - `t.me/reforumspace`
  - `t.me/ksm_lt`
- `https://www.meetup.com`
- `https://www.vilnius-events.lt/`
- `https://www.kaveikti.lt/renginiai/vilniuje`

Future or uncertain sources:

- Facebook groups. Useful event data may exist there, but the account is not verified.
- Telegram source discovery for additional public channels.
- Local Logseq files. Not part of the MVP, but useful later for writing notes or organizing memory.

Credentials may use the user's local API keys where needed.

## Memory

Pino needs persistent memory with two distinct layers:

- Full history: chat history, source observations, generated digests, decisions, and processed items.
- Active memory: facts or preferences explicitly remembered by the user or promoted by Pino because they are useful for future decisions.

Storage can be file-based, SQLite, PostgreSQL, Qdrant, or a combination. For the MVP, prefer the simplest local storage that is easy to inspect and migrate.

Memory must be user-reviewable. Avoid opaque storage that makes it hard to understand why Pino recommended something.

## Configuration

Start with YAML configuration and local files for secrets.

Configuration should cover:

- Enabled integrations.
- Source URLs/channels.
- Schedule settings.
- LLM provider and model selection.
- Ranking goals and keywords.
- Storage paths.
- Digest output preferences.

Avoid hard-coding user preferences that should be editable without code changes.

Current config entry point:

- `config.example.yaml` is the committed sample config.
- `config.local.yaml` is the default local override and should not be committed.
- `INFERCOM_API_KEY` is a local secret file and should not be committed.

Most CLI commands accept `--config/-c`. If omitted, Pino loads `config.local.yaml` when it exists, otherwise `config.example.yaml`.

## Interactive Mode

`pino chat` is the natural-language interface for bounded local tools. It is designed as LLM-to-tools, not as a broad autonomous agent.

The initial tool set is intentionally small:

- `memory.add`
- `memory.list`
- `records.list`
- `digest.create`
- `sources.check`

The committed example config uses the local `echo` provider so the chat loop can be tested without network access. Set `llm.provider` to `infercom` or `ollama` in local config to test real providers.

## Development Notes For Codex

When working on this repository:

- Preserve the local-only deployment assumption.
- Keep integrations isolated; do not let source-specific parsing leak into core ranking or digest logic.
- Prefer typed data models for observations, events, memory entries, and digest results.
- Make CLI flows useful before adding an admin panel.
- Keep storage inspectable and migration-friendly.
- Add tests around deduplication, ranking, config loading, and provider adapters.
- Do not build a broad autonomous agent unless a narrow workflow already works.

## Current Scaffold

The repository is a `uv` workspace with:

- `packages/pino-core`: generic records/artifacts, storage, source adapter protocol, and batch pipeline.
- `apps/pino-cli`: Typer CLI using `pino-core`.

Useful commands:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --all-packages
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run pino check
UV_CACHE_DIR=/tmp/uv-cache uv run pino digest
UV_CACHE_DIR=/tmp/uv-cache uv run pino chat --message "show memory"
```

## Open Questions

- Which storage backend should be used for the first implementation?
- How much historical raw source data should be retained?
- What exact digest format is most useful: terminal output, markdown file, Logseq page, or all of these?
- What is the minimum acceptable Telegram access method for public channels?
- How should Pino decide that an event is important enough to interrupt the normal daily digest?
