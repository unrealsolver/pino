# Progress Log

Short decision log, newest first. Detailed command history lives in git.

## 2026-08-15

- Tightened refinement prompt to reduce reasoning loops: explicit scheduled day bounds, no weekday calculation, and no zero category scores. Verification: refinement tests, full pytest, ruff.
- Added Ollama reasoning diagnostics to `pino refine <id>` by preserving `message.thinking` separately from response content. Verification: provider/refinement/CLI tests, full pytest, ruff.
- Patched refinement prompt so scheduled items use day-level `relevant_from/to` envelopes while exact occurrence times stay in `schedule`. Verification: refinement tests, full pytest, ruff.
- Adjusted refinement prompt so the model preserves source calendar claims instead of verifying/correcting weekdays or date lists. Verification: refinement tests, full pytest, ruff.
- Fixed refinement parsing for MiniMax-style `<think>` output that contains incidental JSON fragments before the real `{"items": [...]}` response. Verification: focused parser smoke, refinement tests, full pytest, ruff.
- Compacted this file from a formal audit trail into a short decision log. Verification: `git diff --check`.
- Refinement prompts stay flat: add `publication_date` only when the source has a publication timestamp. Do not wrap records in `temporal_context`, and do not pretend capture time is publication time.

## 2026-08-12 to 2026-08-14

- Added MiniMax as a first-class OpenAI-compatible provider using `MINIMAX_API_KEY`. Kept simple tasks on M3 because MiniMax did not offer a substantially cheaper suitable text model.
- Made refinement calls more cache-friendly by keeping the static system prompt stable and putting per-record data in the user message.
- Added provider-agnostic LLM usage recording at the completion choke point: input/output/cached tokens, model/provider, operation, duration, and timestamp. Usage is stored in the configured database and exposed through `pino usage`.
- Improved refinement robustness for MiniMax-style output: explicit JSON response shape, stricter JSON recovery, compact source payloads, and no high-entropy storage/Telegram telemetry in the prompt.
- Recurring events are represented as one refinement with `schedule` when possible. Repeated dated model outputs can be coalesced into a weekly recurrence.

## 2026-06-11 to 2026-06-15

- Added optional refinement schedules and Web occurrence projection. `relevant_from`/`relevant_to` remain coarse search/index bounds; concrete recurrence lives in `schedule`.
- Adopted Alembic for storage migrations and made `pino db upgrade/current/history/url` use the configured database target safely.
- Normalized datetime handling so persisted and API datetimes are UTC-aware while display/projection can use the configured local timezone.
- Refactored the Web API into cleaner route/service/repository/dependency boundaries and shared filter objects.

## 2026-06-07 to 2026-06-10

- Built the first Web UI: FastAPI `/api/events` plus React/Vite/Mantine `/event/`.
- Added event filtering, date windows, hidden-event preferences, virtualized rendering, original long-event bounds, and compact event IDs for debugging.
- Standardized frontend data fetching on TanStack Query, large-list rendering on TanStack Virtual, and form state on Mantine form.
- Added `pino refine <id>` dry-run/debug output for prompt, raw response, parsed response, and generated refinements.

## 2026-06-01 to 2026-06-05

- Replaced old goal-specific evaluations with reusable refinement rows: normalized summaries, multi-item extraction, taxonomy scores, and refinement-aware queries.
- Added local SQLite and optional PostgreSQL storage profiles selected by `storage.use`.
- Improved `records.relevant` recall and date filtering, including explicit date ranges, sane null-end behavior, query filtering for named follow-ups, and better chat guidance.
- Updated `pino check` output with source summaries, cursor status, pending refinement/evaluation visibility, and clearer source labels.

## 2026-05-31

- Added durable Telegram cursors so routine checks fetch only messages newer than the last stored channel message.
- Added Vilnius Telegram source configuration for `reforumspace` and `Vilnius_Belarus`, including trusted channel-level location scopes.
- Documented optional source-derived `location_scopes`.
- Added bounded multi-tool chat rounds and parser recovery for models that emit several tool calls or concatenated JSON fragments.

## 2026-05-29 to 2026-05-30

- Moved secret handling to explicit `env:NAME` references with lazy missing-secret behavior and clear warnings.
- Added `pino debug prompts`.
- Added `web.open` as a bounded public HTTP(S) tool for chat event detail lookups.
- Changed chat final answers back to plain text while keeping raw JSON only for tool calls.
- Wrote the repo-local source adapter spec and source backlog.

## 2026-05-24 to 2026-05-27

- Improved chat UX: Markdown rendering, cleaner transcript output, active memory in prompts, configured goals/current time in prompts, and stricter tool-call formatting.
- Added `records.relevant` so chat can retrieve evaluated/relevant records instead of relying on raw lists.
- Removed stored digest artifacts; digests became in-memory results.
- Broadened the `meet_people` goal to include workshops, salons, tastings, niche gatherings, volunteering, and community events.

## 2026-05-20 to 2026-05-22

- Created the source/integration foundation: moved third-party adapters to `pino-integration`, added `vilnius_events`, and added Telegram channel ingestion with Telethon.
- Replaced ambiguous `observed_at` with `relevant_from`/`relevant_to`.
- Made digests and storage queries use relevance-window overlap.
- Added workspace pre-commit tooling with `prek`.
- Created `AGENTS.md` and this progress log.
