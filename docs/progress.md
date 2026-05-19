# Progress Log

Newest entries go first.

## 2026-05-20 01:25 Europe/Vilnius - Codex

- Before: Implement record timing schema change by replacing ambiguous `observed_at` with generic relevance window fields.
- Areas: `Record` model, SQLite schema, tests, integrations if needed, docs/progress.
- After: Replaced `Record.observed_at` with `relevant_from`/`relevant_to`, updated SQLite schema, added source date normalization helpers, and populated relevance windows plus UTC payload fields in current event adapters.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Add query helpers that filter records by relevance-window overlap.

## 2026-05-20 01:23 Europe/Vilnius - Codex

- Before: Revise normalization docs to avoid using `observed_at` as event start time and describe a generic relevance date/window model.
- Areas: `README.md`, `docs/tech-stack.md`, `docs/progress.md`.
- After: Replaced `observed_at` event-time guidance with separate ingestion time, relevance date/window, and paired event start/end payload semantics.
- Verification: `git diff --check`.
- Follow-up: Implement a schema cleanup for `observed_at` and choose `relevant_at` versus `relevant_from`/`relevant_to`.

## 2026-05-20 01:06 Europe/Vilnius - Codex

- Before: Document data normalization direction for records, dates, metadata language, and chat language consistency before implementation.
- Areas: `README.md`, `docs/tech-stack.md`, `docs/progress.md`.
- After: Added normalization policy for canonical English metadata, raw source preservation, timezone-aware UTC event dates, `Record.observed_at`, and session-consistent chat language.
- Verification: `git diff --check`.
- Follow-up: Implement normalization helpers and migrate `kaveikti`/`vilnius_events` adapters to populate canonical UTC fields.

## 2026-05-20 00:32 Europe/Vilnius - Codex

- Before: Add a `vilnius_events` source adapter for ingesting events from vilnius-events.lt.
- Areas: Source adapter, source registry/config, tests, sample config/docs as needed.
- After: Added `vilnius_events` listing parser, registered it, validated config, added sample config/docs, and covered the parser with a fixture test.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`; live parser smoke against `https://www.vilnius-events.lt/en/` returned 68 records.
- Follow-up: Consider detail-page enrichment later if listing cards do not provide enough context for evaluation.

## 2026-05-20 00:24 Europe/Vilnius - Codex

- Before: Add automatic agent guidance for recording progress before and after changes.
- Areas: `AGENTS.md`, `docs/progress.md`.
- After: Created root agent instructions and this progress log template.
- Verification: Not run; documentation-only change.
- Follow-up: None.
