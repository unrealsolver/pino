# Progress Log

Newest entries go first.

## 2026-05-31 00:00 Europe/Vilnius - Codex

- Before: Recover the first valid tool call when a model emits multiple concatenated JSON/wrapped tool-call fragments instead of the required single call.
- Areas: LLM action parser/tests, progress log.
- After: Replaced greedy embedded JSON extraction with incremental decoding and recover the first valid bounded tool call from concatenated output; added regression coverage for the observed multi-`web.open` response and embedded-final-before-tool output.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-llm/tests/test_protocol.py packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Consider a retry/repair round only if models continue emitting malformed shapes that cannot be recovered deterministically.

## 2026-05-30 19:51 Europe/Vilnius - Codex

- Before: Add a bounded web tool so Pino can open event URLs and inspect page details through chat.
- Areas: `pino-core` tools/tests, chat tool descriptions, docs/progress.
- After: Added `web.open` for public HTTP(S) URLs with local/private URL rejection, compact HTML/plain-text extraction, output truncation, prompt/tool docs, and Echo URL tool-call support.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_tools.py packages/pino-core/tests/test_chat.py packages/pino-llm/tests/test_llm_providers.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino debug prompts --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Consider source/domain allowlists or robots-aware fetching if this becomes more than an occasional event-detail lookup.

## 2026-05-30 19:28 Europe/Vilnius - Codex

- Before: Let chat final answers be plain text while keeping JSON only for tool calls and backwards-compatible exact `{"final": ...}` responses.
- Areas: Chat prompt, LLM action parser, echo provider, protocol/chat tests, progress log.
- After: Updated the chat prompt to ask for plain text final answers and raw JSON only for tool calls, made the parser avoid extracting embedded `{"final": ...}` from prose, kept exact `{"final": ...}` compatibility, and changed Echo final responses to plain text.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-llm/tests/test_protocol.py packages/pino-core/tests/test_chat.py packages/pino-llm/tests/test_llm_providers.py apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino chat --config config.example.yaml --history-limit 0 --message hello`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: None.

## 2026-05-30 02:14 Europe/Vilnius - Codex

- Before: Warn when an explicit `env:NAME` secret reference is unresolved, while allowing explicit `null` to stay silent.
- Areas: Config env resolution, docs/tests, progress log.
- After: Added a config logger warning for unresolved `env:NAME` references that includes the env name, config path, and explicit `null` suppression guidance; explicit YAML `null` remains silent.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_config.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino chat --config config.example.yaml --history-limit 0 --message hello`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: None.

## 2026-05-30 02:11 Europe/Vilnius - Codex

- Before: Make missing `env:NAME` references lazy so `config.example.yaml` can document real secret refs without requiring inactive secrets.
- Areas: Config env resolution, sample config, docs/tests, progress log.
- After: Missing `env:NAME` references now resolve to `None`, `config.example.yaml` contains real `env:` references for Infercom and Telegram secrets, docs describe lazy failure, and Infercom has an explicit selected-provider missing-key error.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_config.py packages/pino-llm/tests/test_llm_providers.py packages/pino-integration/tests/test_registry.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino chat --config config.example.yaml --history-limit 0 --message hello`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.yaml`; `git diff --check`.
- Follow-up: None.

## 2026-05-30 01:56 Europe/Vilnius - Codex

- Before: Refactor secret handling to explicit `env:NAME` config references resolved from process environment or `.env`, with clear missing-secret errors and committed `.env.example`.
- Areas: Config loading, LLM provider config, Telegram source settings, sample config/docs/tests, progress log.
- After: Added explicit `env:NAME` resolution with process-env-over-`.env` priority, moved Infercom to `api_key`, made Telegram use resolved `settings.api_id`/`settings.api_hash`, added `.env.example`, updated docs/sample/local config, and migrated the existing ignored Infercom key file into ignored `.env`.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_config.py packages/pino-integration/tests/test_registry.py packages/pino-integration/tests/test_telegram.py packages/pino-llm/tests/test_llm_config.py packages/pino-llm/tests/test_llm_providers.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Remove the legacy ignored `INFERCOM_API_KEY` file later after confirming no scripts still read it.

## 2026-05-29 20:23 Europe/Vilnius - Codex

- Before: Document a clear repo-local source adapter spec so a friend or coding agent can add custom web/Telegram parsers without a plugin system.
- Areas: `docs/source-spec.md`, README source section, `docs/sources.md`, docs/progress.
- After: Added a repo-local source adapter contract, record shape, registry/config steps, parser guidelines, test checklist, and coding-agent prompt.
- Verification: `git diff --check`.
- Follow-up: Consider adding a concrete adapter template only after the first friend-written source reveals missing pieces.

## 2026-05-29 19:31 Europe/Vilnius - Codex

- Before: Add a simple future-proof debug command that prints currently rendered prompts without extra arguments.
- Areas: `pino-core` chat/evaluation prompt rendering, CLI debug command, tests, docs/progress.
- After: Added `pino debug prompts`, backed by shared rendered chat and evaluation system prompt helpers.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_chat.py packages/pino-core/tests/test_evaluation.py apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino debug prompts --config config.example.yaml`; `git diff --check`.
- Follow-up: Add selector flags only when there are enough prompt surfaces to justify them.

## 2026-05-29 02:13 Europe/Vilnius - Codex

- Before: Streamline `pino check` with derived evaluation status/counts so new and pending unevaluated records are visible before evaluation.
- Areas: `pino-core` storage/tools, CLI check output, tests, docs/progress.
- After: Added derived record evaluation status/count helpers, included total/new pending evaluation counts in `CheckResult`, printed them from `pino check` and `sources.check`, and labeled unevaluated records in list/relevant tool output.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_storage.py packages/pino-core/tests/test_pipeline.py packages/pino-core/tests/test_tools.py apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino check --config config.example.yaml`; `git diff --check`.
- Follow-up: Add an opt-in `pino check --evaluate` path that evaluates pending/new records after the fast check summary.

## 2026-05-29 01:57 Europe/Vilnius - Codex

- Before: Store missing integration recommendations in a new source planning document.
- Areas: `docs/sources.md`, `docs/progress.md`.
- After: Added a source integration backlog covering current source types, priority candidates, and implementation notes.
- Verification: `git diff --check`.
- Follow-up: Implement `meetup` first, then ticketing and Resident Advisor sources.

## 2026-05-27 15:50 Europe/Berlin - Codex

- Before: Broaden the `meet_people` evaluation goal in example and real config to include niche workshops, salons, tastings, and cultural gatherings that attract interesting people.
- Areas: `config.example.yaml`, local `config.yaml`, `docs/progress.md`.
- After: Updated `meet_people` to include interesting new people plus small workshops, tastings, cultural salons, lectures, niche gatherings, volunteering, community events, and natural-conversation settings.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_config.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.yaml`; `git diff --check`.
- Follow-up: Re-run evaluation for affected records if existing scores should reflect the broader goal.

## 2026-05-27 15:07 Europe/Berlin - Codex

- Before: Add simple visible progress messages to `pino evaluate` so long evaluation runs do not look idle.
- Areas: `packages/pino-core/src/pino_core/evaluation.py`, `apps/pino-cli/src/pino_cli/main.py`, tests, progress log.
- After: Added structured evaluation progress events and CLI forward-only messages for selected/evaluating/evaluated/skipped records.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_evaluation.py apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: None.

## 2026-05-25 21:57 Europe/Vilnius - Codex

- Before: Implement `records.relevant` so chat can actually see the documented evaluated-record retrieval tool.
- Areas: `packages/pino-core/src/pino_core/tools.py`, `packages/pino-core/tests/test_tools.py`, `packages/pino-core/src/pino_core/chat.py`, `packages/pino-llm/src/pino_llm/providers.py`, `docs/progress.md`.
- After: Implemented `records.relevant` with relevance-window, `min_score`, and `goals` filtering; updated the chat prompt example and Echo provider to use it.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_tools.py packages/pino-core/tests/test_chat.py packages/pino-llm/tests/test_llm_providers.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino chat --config config.example.yaml --history-limit 0 --debug --message "list records"`. Full `uv run pytest` was not run because escalation was rejected by the environment usage limit.
- Follow-up: Run full `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` when escalation is available again.

## 2026-05-25 21:48 Europe/Vilnius - Codex

- Before: Document v1 evaluated record retrieval for chat recommendations without targeted record lookup.
- Areas: `README.md`, `docs/tech-stack.md`, `docs/progress.md`.
- After: Specified `records.relevant` as the preferred chat recommendation tool with `limit`, `days`, `min_score`, and `goals`; kept `records.list` as raw/debug; deferred targeted `records.get`.
- Verification: `git diff --check`.
- Follow-up: Implement `records.relevant` in `pino-core` tools and tests.

## 2026-05-25 20:38 Europe/Vilnius - Codex

- Before: Add configured goals and current local time to the chat system prompt.
- Areas: `packages/pino-core/src/pino_core/chat.py`, `packages/pino-core/tests/test_chat.py`, `apps/pino-cli/src/pino_cli/main.py`, `docs/progress.md`.
- After: Chat prompts now include current `Europe/Vilnius` time plus configured evaluation goals as a separate `Goals` section before active memory; CLI passes `config.evaluation.goals` into `ChatAgent`.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Make record retrieval evaluation-aware so chat can use the same goals when fetching event candidates.

## 2026-05-25 20:27 Europe/Vilnius - Codex

- Before: Tighten chat tool-call prompt instructions after malformed `[TOOL_CALL]` text leaked to chat output.
- Areas: `packages/pino-core/src/pino_core/chat.py`, `packages/pino-core/src/pino_core/tools.py`, `packages/pino-core/tests/test_chat.py`, `packages/pino-llm/src/pino_llm/protocol.py`, `packages/pino-llm/tests/test_protocol.py`, `docs/progress.md`.
- After: Chat prompt now demands one raw JSON object, forbids provider-specific wrappers/loose syntax/CLI-style flags, tool descriptions use JSON argument examples, and the parser handles the observed loose wrapped tool-call shape.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-llm/tests/test_protocol.py packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Consider a model retry loop for malformed tool calls if other invalid formats still leak.

## 2026-05-25 20:01 Europe/Vilnius - Codex

- Before: Remove stored digest artifacts because artifacts are not a current product goal.
- Areas: `packages/pino-core/src/pino_core/models.py`, `packages/pino-core/src/pino_core/storage.py`, `packages/pino-core/src/pino_core/pipeline.py`, `packages/pino-core/tests/test_pipeline.py`, CLI/docs/progress.
- After: Removed the `Artifact` model/export/table/store API; digest generation now returns an in-memory `DigestResult` and no longer writes digest output to storage.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_pipeline.py packages/pino-core/tests/test_storage.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Existing local SQLite files may still contain an unused legacy `artifacts` table; no cleanup migration was added.

## 2026-05-25 01:50 Europe/Vilnius - Codex

- Before: Exclude persisted tool messages from chat context and inject active memory into chat prompts.
- Areas: `packages/pino-core/src/pino_core/chat.py`, `packages/pino-core/src/pino_core/config.py`, `packages/pino-core/tests/test_chat.py`, `apps/pino-cli/src/pino_cli/main.py`, `config.example.yaml`, `docs/progress.md`.
- After: Persisted `role=tool` messages are excluded from normal chat history/context; active memory is appended to the system prompt with `chat.active_memory_limit`; current-turn tool context is preserved.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Add evaluation-aware record retrieval next if chat recommendations still lean on raw records.

## 2026-05-24 14:20 Europe/Vilnius - Codex

- Before: Format stored chat history messages with the same Rich Markdown renderer, and keep historical tool-call display optional when persisted data exists.
- Areas: `apps/pino-cli/src/pino_cli/main.py`, `apps/pino-cli/tests/test_main.py`, `docs/progress.md`.
- After: Stored user/assistant transcript lines render through Rich Markdown; persisted tool messages remain ignored by normal history display.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Add persisted user-facing tool history later only if the storage model captures tool-call summaries worth showing.

## 2026-05-24 13:12 Europe/Vilnius - Codex

- Before: Make chat output nicer while keeping `rich`: render basic Markdown and show compact normal-mode tool use.
- Areas: `apps/pino-cli/src/pino_cli/main.py`, `apps/pino-cli/tests/test_main.py`, `docs/progress.md`.
- After: Chat and digest bodies render through Rich Markdown; normal chat prints compact tool-call lines while `--debug` keeps detailed tables.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Add true live tool callbacks later if forward-only post-response tool lines are not enough.

## 2026-05-22 00:47 Europe/Vilnius - Codex

- Before: Add a Telegram channel integration in `pino-integration` without adding Telethon or Telegram-specific concerns to `pino-core`.
- Areas: Integration package, source config settings, sample config/docs, tests, dependency constraints.
- After: Added `telegram_channel` source using Telethon, generic `SourceConfig.settings`, parser/factory/fetch tests with fake clients, disabled `afisha-vilnius` sample config, and exact `telethon==1.43.2` workspace constraint.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv lock`; `UV_CACHE_DIR=/tmp/uv-cache uv sync --all-packages`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `git diff --check`; `PREK_HOME=/tmp/prek-cache UV_CACHE_DIR=/tmp/uv-cache uv run prek run --all-files`.
- Follow-up: Run a live Telegram fetch after local API credentials and session login are configured.

## 2026-05-21 23:56 Europe/Vilnius - Codex

- Before: Move third-party source integrations out of `pino-core` into a new `pino-integration` workspace package and centralize exact dependency constraints.
- Areas: Workspace/package metadata, integration modules and tests, registry wiring, docs/progress.
- After: Added `packages/pino-integration`, moved `kaveikti` and `vilnius_events` adapters/tests/fixtures there, made the CLI use the integration registry, removed integration parser deps and source-specific registry wiring from `pino-core`, and moved direct dependency versions to exact workspace constraints.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv lock`; `UV_CACHE_DIR=/tmp/uv-cache uv sync --all-packages`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `git diff --check`; `PREK_HOME=/tmp/prek-cache UV_CACHE_DIR=/tmp/uv-cache uv run prek run --all-files`.
- Follow-up: None.

## 2026-05-21 00:09 Europe/Vilnius - Codex

- Before: Make digests use `relevant_from`/`relevant_to` so output favors current and upcoming actionable records.
- Areas: Storage query helpers, digest service, CLI options, tests, docs, progress log.
- After: Added relevance-window overlap queries, made digest default to the next 14 days, added `pino digest --days`, included local time/location/summary in digest lines, and covered filtering with tests.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `PREK_HOME=/tmp/prek-cache UV_CACHE_DIR=/tmp/uv-cache uv run prek run --all-files`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino digest --help`; `git diff --check`.
- Follow-up: Decide whether digest should exclude undated records once real event sources are the default.

## 2026-05-20 23:28 Europe/Vilnius - Codex

- Before: Add `prek` pre-commit tooling for the workspace.
- Areas: Tooling config, README, progress log, lockfile if dependency resolution is needed.
- After: Added `prek` as a dev dependency, created local hooks for `ruff check .` and `pytest`, and documented install/run commands.
- Verification: `PREK_HOME=/tmp/prek-cache UV_CACHE_DIR=/tmp/uv-cache uv run prek validate-config .pre-commit-config.yaml`; `PREK_HOME=/tmp/prek-cache UV_CACHE_DIR=/tmp/uv-cache uv run prek run --all-files`; `git diff --check`.
- Follow-up: None.

## 2026-05-20 03:36 Europe/Vilnius - Codex

- Before: Make interactive CLI history render like a chat transcript instead of a table with raw roles/tool calls.
- Areas: CLI history display, tests, progress log.
- After: Changed interactive history display to `Boss>`/`Pino>` transcript lines and filtered tool messages from normal-mode display.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-05-20 02:39 Europe/Vilnius - Codex

- Before: Use existing chat `history_limit` for both agent context and interactive CLI history display, with tests proving the agent receives N previous messages.
- Areas: Chat agent, CLI display, tests, progress log.
- After: Updated chat context assembly so `history_limit` means N previous messages plus the current user message, added interactive CLI recent-history display, and covered both paths with tests.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Consider whether normal CLI display should hide `tool` messages while keeping them in agent context.

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
