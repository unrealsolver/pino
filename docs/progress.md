# Progress Log

Newest entries go first.

## 2026-06-09 18:25 Europe/Vilnius - Codex

- Before: Rework the TanStack Virtual hide/show drift fix because stable item keys plus `measure()` did not resolve row offset errors.
- Areas: Frontend virtualized event list measurement/reset behavior, tests, docs/progress.
- After: Completed at 18:29. Moved window virtualization into a keyed `VirtualEventList` child so row identity changes remount the virtualizer, kept TanStack Virtual keyed by stable day/event row keys, and replaced render-time `listRef.current?.offsetTop` reads with layout-effect-managed `scrollMargin` state to prevent offset jumps after hide/reveal or other visibility renders.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-09 17:56 Europe/Vilnius - Codex

- Before: Fix TanStack Virtual row-position drift after hiding/revealing events or changing visibility.
- Areas: Frontend virtualizer row identity/measurement, tests, docs/progress.
- After: Completed at 17:59. Added stable TanStack Virtual item keys based on the flattened day/event row keys and forced the virtualizer to remeasure whenever the visible row list changes, preventing stale index-based measurements after hide/show or filter visibility changes.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-09 15:36 Europe/Vilnius - Codex

- Before: Normalize Web UI styling toward Mantine component props and keep CSS only for layout mechanics, using Mantine xs-xl token variables where CSS remains.
- Areas: Frontend route component props, CSS, tests, docs/progress.
- After: Completed at 15:39. Moved filter/empty/event row/day-header visual styling to Mantine props where practical (`bg`, `withBorder`, `p`, `radius`, `c`, `opacity`, `m`) and trimmed CSS back toward virtualization/grid/layout concerns; remaining CSS now uses Mantine variables for spacing, radius, shadows, and palette tokens instead of hard-coded rem/hex values where practical.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-09 03:06 Europe/Vilnius - Codex

- Before: Persist Web UI hidden event preferences in local storage using Mantine's `useLocalStorage`.
- Areas: Frontend hide/show state, tests, docs/progress.
- After: Completed at 03:07. Replaced in-memory hidden event/show-hidden state with Mantine `useLocalStorage`, storing hidden event ids under `pino-web-hidden-event-ids` and the `Show hidden` checkbox under `pino-web-show-hidden-events`; kept derived `Set` lookup for rendering.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-09 03:03 Europe/Vilnius - Codex

- Before: Make Web UI day headers harder to miss while keeping the virtualized list simple and non-sticky.
- Areas: Frontend day-header styling, tests, docs/progress.
- After: Completed at 03:04. Made day headers more prominent with a compact tinted band, stronger amber accent border, heavier title text, thicker separator line, and subtle depth while avoiding sticky behavior that conflicts with the absolute-positioned virtual rows.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: If stronger static headers still are not enough, implement a separate floating current-day indicator driven by the virtualizer visible range instead of CSS sticky.

## 2026-06-08 23:41 Europe/Vilnius - Codex

- Before: Refactor Web UI hide/show controls to use a global `Show hidden` checkbox, passive day hidden counts, and per-row eye/eye-off icons.
- Areas: Frontend event route hide state rendering, styles, tests, docs/progress.
- After: Completed at 23:42. Replaced the previous per-day undo button with a header `Show hidden` checkbox, changed day headers to passive `N hidden` text, kept hidden rows in the virtual list only when `Show hidden` is enabled, and made visible rows use an eye-off icon while hidden rows use a regular eye icon to restore them.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-08 23:21 Europe/Vilnius - Codex

- Before: Fix Web UI long-event overflow rendering showing `NaNd` when original event bounds are missing or invalid.
- Areas: Frontend event overflow formatter, tests, docs/progress.
- After: Completed at 23:22. Made `original_starts_at`/`original_ends_at` optional in the frontend response type and hardened the overflow formatter to ignore missing or invalid dates instead of rendering `NaNd`; added regression tests for missing and invalid original bounds.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Restart the frontend dev server if it does not hot-reload the type/formatter change.

## 2026-06-08 23:02 Europe/Vilnius - Codex

- Before: Show long-event overflow context in the Web UI while keeping visible event dates clipped to the active filter window.
- Areas: Web API event response shape, frontend event time metadata rendering, tests, docs/progress.
- After: Completed at 23:04. Added original event bounds to `/api/events` responses while keeping visible `starts_at`/`ends_at` clipped to the active filter window; the UI now renders clipped multi-day occurrences as `All day` with an overflow marker like `-5d | +20d` when the original event extends before/after the visible range.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-web/tests/test_app.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/pino-web/src/pino_web apps/pino-web/tests/test_app.py`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Restart any running `pino-web` API process to expose the new original-bound fields.

## 2026-06-08 22:58 Europe/Vilnius - Codex

- Before: Diagnose and fix `/api/events` returning events outside an explicit `date_from`/`date_to` range.
- Areas: Web API date parsing/window handling, storage event query tests, docs/progress.
- After: Completed at 22:59. Kept storage overlap matching intact, but changed Web API event serialization to clip long-running event `starts_at`/`ends_at` to the requested window so `/api/events?date_from=2026-06-07T21:00:00.000Z&date_to=2026-07-08T21:00:00.000Z` cannot return response timestamps outside that range.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-web/tests/test_app.py packages/pino-core/tests/test_storage.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/pino-web/src/pino_web apps/pino-web/tests/test_app.py packages/pino-core/src/pino_core/storage.py packages/pino-core/tests/test_storage.py`; direct in-memory smoke check for the reported UTC window; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `git diff --check`.
- Follow-up: Restart any running `pino-web` API process to pick up the serialization fix.

## 2026-06-08 17:45 Europe/Vilnius - Codex

- Before: Improve Web UI large-list performance by defaulting date range to 30 days, adding a `Next month` range extension button, and rendering event rows with TanStack React Virtual.
- Areas: Frontend dependencies, event route date/window behavior, virtualized rendering, tests, docs/progress.
- After: Completed at 21:44. Added `@tanstack/react-virtual` `^3.14.2`; changed the default Web UI date range to today morning through +30 days; made `From` changes and reset actions maintain a 30-day window; added a bottom `Next month` button that extends `dateTo` by another 30 days; replaced full day/event rendering with a window-virtualized flattened list of day headers and visible event occurrences; updated the Web UI spec.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun add @tanstack/react-virtual`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Vite build still succeeds with the existing bundle-size warning; consider code splitting later.

## 2026-06-08 16:01 Europe/Vilnius - Codex

- Before: Add TanStack Query for Web UI API fetching and update `docs/web-ui.md` to include it in the frontend stack.
- Areas: Frontend dependencies/provider/API hook usage, Web UI spec, tests, docs/progress.
- After: Completed at 16:11. Added `@tanstack/react-query` `^5.101.0`, wrapped the app in `QueryClientProvider`, moved event fetching to `useQuery` with stable filter-derived keys and abort-signal forwarding, kept previous data during filter refreshes, and documented TanStack Query in the Web UI frontend stack.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun add @tanstack/react-query`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Vite build still succeeds with a bundle-size warning, now larger after adding TanStack Query; consider code splitting later.

## 2026-06-08 15:46 Europe/Vilnius - Codex

- Before: Update the Web UI from Mantine 8.x to Mantine 9.x and apply any required compatibility fixes.
- Areas: Frontend dependencies, Mantine theme/provider usage, tests, docs/progress.
- After: Completed at 15:48. Updated `@mantine/core`, `@mantine/dates`, and `@mantine/hooks` to `9.3.0`; kept React 19.2.x unchanged; added `defaultRadius: "sm"` to preserve the pre-v9 default radius behavior for future Mantine components.
- Verification: `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun add @mantine/core@9.3.0 @mantine/dates@9.3.0 @mantine/hooks@9.3.0`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Vite build still succeeds with the existing bundle-size warning; consider code splitting later if needed.

## 2026-06-08 15:41 Europe/Vilnius - Codex

- Before: Compact the recent Web UI/frontend progress entries into a shorter summary while preserving the substantive implementation and verification history.
- Areas: `docs/progress.md`.
- After: Completed at 15:41. Replaced four detailed Web UI/frontend entries from 2026-06-07 with one compact implementation summary and retained verification/follow-up highlights.
- Verification: `git diff --check`.
- Follow-up: None.

## 2026-06-07 19:09-22:28 Europe/Vilnius - Codex

- Before: Implement and iterate on the first Web UI slice from `docs/web-ui.md`: FastAPI event query API plus React/Vite/Mantine SPA at `/event/`.
- Areas: `apps/pino-web`, `web`, storage event query helpers, tests, `pyproject.toml`, `uv.lock`, `docs/progress.md`.
- After: Added `pino-web` FastAPI app with `/api/events`, 60 rpm in-memory throttling, bounded query validation, local-time event serialization, explicit `--config`/host/port CLI options, and storage-backed filtering by date overlap, category, score, and text. Added Vite React/Mantine SPA at `/event/` with amber/wood styling, filters, English UI with `en-LT` regional date/time formatting and `YYYY-MM-DD HH:mm` picker display, calendar-style multi-day expansion, per-event `Hide event` controls that hide all occurrences, and one-step per-day `Hide back` restore for the last hidden event.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv lock`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun install`; `UV_CACHE_DIR=/tmp/uv-cache uv sync --all-packages`; targeted backend/frontend tests; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run test`; `BUN_TMPDIR=/tmp BUN_INSTALL=/tmp/bun-install bun run build`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`; local `curl` smoke checks for API and `/event/`.
- Follow-up: Vite build succeeds but reports a React/Mantine bundle-size warning; consider code splitting if the UI grows. If expanded long-running events make the default one-year view too dense, add a narrower default end date or an ongoing-events lane.

## 2026-06-05 01:57 Europe/Vilnius - Codex

- Before: Fix confusing chat follow-ups where Pino contradicts a previous `records.relevant` result instead of resolving a named event from prior context or targeted lookup.
- Areas: Chat prompt/tool guidance, relevant-record lookup behavior, tests, progress log.
- After: Completed at 01:59. Added a `query` filter to `records.relevant` so named follow-up events can be resolved inside the known date window, kept URLs in the filtered result for `web.open`, and updated the chat prompt to resolve named events before opening their URLs instead of rerunning broad lists.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_tools.py packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check packages/pino-core/src/pino_core/tools.py packages/pino-core/src/pino_core/chat.py packages/pino-core/tests/test_tools.py packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Watch live chat behavior to confirm the model performs the second `web.open` round after resolving a named event URL.

## 2026-06-04 01:47 Europe/Vilnius - Codex

- Before: Format non-chat CLI source labels as `{web|tg}:{name}` while leaving Pino chat output unchanged.
- Areas: CLI source display, tests, progress log.
- After: Completed at 01:49. Added source-kind metadata for web and Telegram adapters, carried it through check results, and formatted non-chat CLI source labels as `web:{name}` or `tg:{name}` in `pino check` and `pino sources list`.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-cli/tests/test_main.py packages/pino-core/tests/test_pipeline.py packages/pino-integration/tests/test_kaveikti.py packages/pino-integration/tests/test_vilnius_events.py packages/pino-integration/tests/test_telegram.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/pino-cli/src/pino_cli/main.py apps/pino-cli/tests/test_main.py packages/pino-core/src/pino_core/pipeline.py packages/pino-core/tests/test_pipeline.py packages/pino-core/src/pino_core/sources.py packages/pino-integration/src/pino_integration/kaveikti.py packages/pino-integration/src/pino_integration/vilnius_events.py packages/pino-integration/src/pino_integration/telegram.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino check --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-04 01:43 Europe/Vilnius - Codex

- Before: Clarify `pino check` cursor status so cursor-aware sources with no new messages do not look the same as non-cursor sources.
- Areas: Check result model, CLI source table, tests, progress log.
- After: Completed at 01:45. Added explicit cursor statuses (`unsupported`, `none`, `unchanged`, `updated`) and render non-cursor sources as `-` while cursor-aware sources with no new messages show `unchanged`.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-cli/tests/test_main.py packages/pino-core/tests/test_pipeline.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/pino-cli/src/pino_cli/main.py apps/pino-cli/tests/test_main.py packages/pino-core/src/pino_core/pipeline.py packages/pino-core/tests/test_pipeline.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino check --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-04 01:16 Europe/Vilnius - Codex

- Before: Make `pino check` output more useful and scannable while preserving existing fetch/insert/duplicate/refinement information.
- Areas: CLI check output, tests, progress log.
- After: Completed at 01:18. Added per-source check statistics to `CheckResult`, rendered `pino check` as a Rich summary panel plus source breakdown and new-record preview, and kept the empty-new-record case explicit.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-cli/tests/test_main.py packages/pino-core/tests/test_pipeline.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check apps/pino-cli/src/pino_cli/main.py apps/pino-cli/tests/test_main.py packages/pino-core/src/pino_core/pipeline.py packages/pino-core/tests/test_pipeline.py packages/pino-core/src/pino_core/__init__.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino check --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Consider per-source timing/error capture later if source checks become slow or flaky.

## 2026-06-04 00:25 Europe/Vilnius - Codex

- Before: Fix date-range retrieval returning March events for June queries because null `relevant_to` is treated as an indefinitely ongoing event.
- Areas: Relevant refinement storage query, SQLite regression tests, progress log.
- After: Completed at 00:27. Changed overlap logic so `relevant_to = null` means a point event at `relevant_from`, not an indefinitely ongoing event; added SQLite regression coverage for excluding past null-end events and including in-window null-end events.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_storage.py packages/pino-core/tests/test_tools.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check packages/pino-core/src/pino_core/storage.py packages/pino-core/tests/test_storage.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Run one live PostgreSQL smoke query if the model still returns stale null-end events.

## 2026-06-04 00:15 Europe/Vilnius - Codex

- Before: Remove the bare `date` filter from `records.relevant` and use `date_from`/`date_to` consistently for single-day and range queries.
- Areas: Relevant-record tool arguments, chat prompt, tests, progress log.
- After: Completed at 00:16. Removed bare `date` handling from the tool, changed single-day examples to `date_from == date_to`, and updated prompt/tests accordingly.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_chat.py packages/pino-core/tests/test_tools.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check packages/pino-core/src/pino_core/tools.py packages/pino-core/src/pino_core/chat.py packages/pino-core/tests/test_tools.py packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: None.

## 2026-06-04 00:14 Europe/Vilnius - Codex

- Before: Clarify weekend-style event queries so chat uses explicit `records.relevant` date ranges rather than broad day counts.
- Areas: Chat prompt, tests, progress log.
- After: Completed at 00:15. Added chat prompt guidance and an example for weekend-style range queries using `date_from`/`date_to`, and extended the prompt regression test.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_chat.py packages/pino-core/tests/test_tools.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check packages/pino-core/src/pino_core/chat.py packages/pino-core/tests/test_chat.py`.
- Follow-up: None.

## 2026-06-04 00:08 Europe/Vilnius - Codex

- Before: Diagnose and fix `records.relevant`/chat behavior after Pino claimed no June events despite a June 5 refinement row being present in the database.
- Areas: Relevant-record tool path, chat/tool diagnostics, tests, progress log.
- After: Completed at 00:12. Added explicit local-date and date-range arguments to `records.relevant`, added a query-window header to tool output, taught the chat prompt to use `date` for specific-day requests like next Friday, and covered the June 5 Macau-film row shape with a regression test.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_tools.py packages/pino-core/tests/test_chat.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Watch the live MiniMax behavior for whether it now chooses `date`; no exact live chat rerun was performed after the interrupted diagnostic.

## 2026-06-03 14:04 Europe/Vilnius - Codex

- Before: Improve retrieval recall after Pino missed compatible events present in raw `records.list`, starting with the current `records.relevant` candidate truncation and documenting the pgvector/embedding follow-up.
- Areas: Relevant-record retrieval, tests, refinement/retrieval docs, progress log.
- After: Completed at 14:05. Changed `records.relevant` to scan a larger bounded candidate window before category filtering, rank filtered results by compatibility score, exposed `scan_limit`, added a regression test for later-window compatible events, and documented retrieval debugging plus the PostgreSQL/pgvector direction.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_tools.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `git diff --check`.
- Follow-up: Add retrieval diagnostics for unrefined/date-missing/non-event/low-score misses; then add refinement embeddings and optional PostgreSQL `pgvector` nearest-neighbor candidate expansion.

## 2026-06-01 02:48 Europe/Vilnius - Codex

- Before: Replace flat storage path/URL selection with named storage backends selected by `storage.use`, allowing explicit local SQLite and VPS PostgreSQL profiles while keeping unselected profiles lazy.
- Areas: Storage config model/path resolution, local/example config, tests, docs, progress log.
- After: Completed at 03:13. Added typed named storage backends with arbitrary profile names, `storage.use` selection, per-backend SQLite path resolution, lazy target validation, `local`/`pg_vps` example and ignored local config profiles, docs, and tests.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_config.py apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino memory list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino memory list --config config.yaml`; `git diff --check`.
- Follow-up: Set `PINO_DATABASE_URL`, change `storage.use` to `pg_vps`, and run a live VPS smoke test. Missing env references still warn even for unselected backends by design.

## 2026-06-01 02:35 Europe/Vilnius - Codex

- Before: Add single-tenant PostgreSQL storage support for VPS-backed development state while preserving SQLite as the local default and keeping existing SQLite callers compatible.
- Areas: Storage config/store construction/schema initialization, PostgreSQL driver dependency/lockfile, tests, example env/config, docs, progress log.
- After: Completed at 02:43. Added URL-configured `DatabaseStore`, Psycopg 3 support, fresh PostgreSQL schema initialization, SQLite compatibility wrapper and migration gating, env/config examples, local ignored `env:PINO_DATABASE_URL` wiring, docs, and tests.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv lock`; `UV_CACHE_DIR=/tmp/uv-cache uv sync --all-packages`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; offline PostgreSQL DDL compilation with SQLAlchemy `create_mock_engine`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino memory list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino memory list --config config.yaml`; `git diff --check`.
- Follow-up: Populate `PINO_DATABASE_URL` and run a live VPS smoke test. Cross-database schema migrations remain future work; current PostgreSQL support initializes a fresh database.

## 2026-06-01 01:37 Europe/Vilnius - Codex

- Before: Implement the first end-to-end generic refinement slice without embeddings: raw-only records, reusable multi-item refinements, taxonomy scores, refinement-aware queries, and a `pino refine` CLI while keeping a temporary `pino evaluate` alias.
- Areas: Core models/config/storage/refinement service/pipeline/tools, CLI, source adapters, tests, docs, progress log.
- After: Replaced active goal-specific evaluations with reusable multi-item refinements; added `pino refine` plus temporary `pino evaluate` alias; moved relevance queries/digests and pending counts to refinements; made adapters capture source-native data only; separated reusable taxonomy config from private profile goals; and updated docs. Dense embeddings remain intentionally deferred.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest apps/pino-cli/tests/test_main.py packages/pino-core/tests/test_pipeline.py packages/pino-core/tests/test_refinement.py packages/pino-core/tests/test_storage.py packages/pino-core/tests/test_tools.py packages/pino-integration/tests`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino refine --help`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino evaluate --help`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino debug prompts --config config.example.yaml`; `git diff --check`.
- Follow-up: Add private profile weighting beyond explicit category filters; benchmark Ollama `bge-m3` later; add deterministic refinement shortcuts only if measurements justify them; physically clean inert legacy SQLite evaluation/date columns only if worthwhile.

## 2026-05-31 20:54 Europe/Vilnius - Codex

- Before: Write a lean refinement-layer design proposal that removes mixed structured-data ownership from raw records, supports reusable taxonomy scoring, and evaluates whether embedding models can complement or replace explicit category scores.
- Areas: Refinement design docs, progress log.
- After: Added `docs/refinements.md` with a lean target model: raw capture-only records, one normalized refinement table, derived multi-event handling, source-derived geographic scope, additive taxonomy versions, private query-time ranking, and optional embedding-based taxonomy projection. Linked the proposal from the current source adapter spec.
- Verification: `git diff --check`.
- Follow-up: Review the seed taxonomy against captured records, then benchmark embedding-derived category projections on a small labeled sample before deciding whether any categories need an LLM classifier pass.

## 2026-05-31 02:55 Europe/Vilnius - Codex

- Before: Refactor Telegram ingestion to persisted cursor-style checks so routine runs request only messages newer than the last successfully stored channel message.
- Areas: Core source protocol/pipeline/storage, Telegram adapter/tests, docs, progress log.
- After: Added optional cursor-aware source ingestion with durable SQLite `source_cursors`, switched Telegram checks to a bounded first-run bootstrap followed by complete `min_id` incremental reads, documented the behavior, and covered pipeline persistence plus Telegram request shape.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_pipeline.py packages/pino-core/tests/test_storage.py packages/pino-integration/tests/test_telegram.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Existing databases intentionally bootstrap each Telegram source on its next check because they do not yet have cursor rows. Consider an explicit cursor reset CLI only if source maintenance needs it.

## 2026-05-31 02:14 Europe/Vilnius - Codex

- Before: Add `t.me/Vilnius_Belarus` as another Vilnius-scoped Telegram source.
- Areas: Example and local source config, progress log.
- After: Added disabled committed and enabled local `vilnius-belarus` Telegram sources with channel-level `LT/vilnius` scope metadata.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.yaml`; `git diff --check`.
- Follow-up: Run an intentional live Telegram fetch when desired; it contacts Telegram and may update the local session file.

## 2026-05-31 02:08 Europe/Vilnius - Codex

- Before: Add `t.me/reforumspace` as a Vilnius Telegram source and carry its trustworthy channel-level `LT/vilnius` scope into captured message payload/provenance.
- Areas: Telegram adapter/tests, example and local source config, progress log.
- After: Added disabled committed and enabled local `reforumspace-vilnius` Telegram sources, added optional Telegram `settings.location_scopes`, and copy configured channel scopes into message payload with `location_scope_source: channel_config` provenance.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-integration/tests/test_telegram.py packages/pino-integration/tests/test_registry.py packages/pino-core/tests/test_config.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.example.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino sources list --config config.yaml`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `git diff --check`.
- Follow-up: Run an intentional live Telegram fetch when desired; it contacts Telegram and may update the local session file.

## 2026-05-31 01:36 Europe/Vilnius - Codex

- Before: Document optional source-derived location scopes for event records without adding config defaults or required schema fields.
- Areas: `docs/source-spec.md`, `README.md`, `docs/tech-stack.md`, progress log.
- After: Documented optional `payload.location_scopes` with `LT/vilnius`, multi-city, and explicit `LT/*` examples; kept human-facing `payload.location`, scope evidence in provenance when useful, and no config defaults or required top-level schema fields.
- Verification: `git diff --check`.
- Follow-up: Add scopes to individual adapters only when each source provides trustworthy evidence.

## 2026-05-31 00:12 Europe/Vilnius - Codex

- Before: Add first-class bounded multi-tool chat rounds for MiniMax-style batched tool requests, with parallel execution limited to safe read-only tools.
- Areas: Chat config/agent, LLM action protocol, CLI debug output, sample config, tests, progress log.
- After: Added `chat.max_tools_per_round` with default `3`, normalized explicit `{"tools": [...]}`, wrapped arrays, and concatenated JSON fragments into multi-call actions, executed safe read-only batches in parallel while keeping other tools sequential, and expanded prompt/debug output for multi-tool rounds.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-llm/tests/test_protocol.py packages/pino-core/tests/test_chat.py packages/pino-core/tests/test_config.py apps/pino-cli/tests/test_main.py`; `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`; `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`; `UV_CACHE_DIR=/tmp/uv-cache uv run pino debug prompts --config config.example.yaml`; `git diff --check`.
- Follow-up: Review real MiniMax debug traces and adjust the cap only if three independent calls per round is too restrictive.

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
