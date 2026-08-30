# Progress Log

Short decision log, newest first. Detailed command history lives in git.

## 2026-08-30 22:24 EEST — /root

- Intended: schema-lifecycle cleanup step 1 only—add an idempotent portable Alembic baseline so an empty SQLite or PostgreSQL database can enter the existing migration chain; do not change runtime `init_schema` behavior yet.
- Areas: migration baseline/ancestry, fresh-database migration tests, and this progress log.
- Result (22:26 EEST): added base revision `20260610_0000` for the five portable pre-schedule tables and linked the existing migration chain to it. The baseline creates missing tables but tolerates pre-Alembic tables, while later revisions still add schedule and usage storage. Runtime `init_schema` is unchanged.
- Verification: full `pytest` passed (169 tests), Ruff passed for all packages/apps, migration history resolves as one base-to-head chain, and `git diff --check` passed. PostgreSQL execution remains untested without a live server. Follow-up: await review before legacy-column reconciliation.

## 2026-08-30 21:36 EEST — /root

- Intended: final schedule-query step—stream bounded coarse candidates, perform exact schedule matching in Core before page limits, and keep Web projection consistent; no occurrence table, SQLite index, or canonical-model change.
- Areas: Core storage query path, Web schedule-result expectations, focused regression tests, and this progress log.
- Result (21:39 EEST): relevant/event queries now stream one ordered candidate result set in 200-row fetches, reject nonmatching schedules before they consume the requested limit, and stop after a 5,000-candidate safety cap. PostgreSQL retains its multirange prefilter; SQLite performs the same exact pass over coarse candidates. Web still expands accepted schedules into display occurrences.
- Verification: full `pytest` passed (169 tests), Ruff passed for all packages/apps, and `git diff --check` passed. Live PostgreSQL execution and planner behavior remain for acceptance testing; a cap-exhausted query can intentionally return a short page. Follow-up: review and acceptance testing.

## 2026-08-30 19:14 EEST — /root

- Intended: step 4 only—maintain the PostgreSQL derived schedule index in the same refinement-replacement transaction and apply its timezone-aware weekly overlap as a PostgreSQL candidate prefilter; do not change SQLite behavior or add exact filtering to generic Core queries yet.
- Areas: schedule query-pattern compilation, PostgreSQL storage write/read paths, focused tests, and this progress log.
- Result (19:19 EEST): scheduled replacements now write the derived multirange in the same PostgreSQL transaction, and relevant-event reads apply a timezone-aware `&&` candidate gate while retaining unindexed rows. Query and stored masks conservatively cover inclusive minute boundaries and DST rollback, allowing false positives but not false negatives. SQLite and generic exact filtering are unchanged.
- Verification: full `pytest` passed (168 tests), Ruff passed for all packages, and `git diff --check` passed. PostgreSQL DDL/query plans were not exercised against a live server. Follow-up: await review before the SQLite fallback step.

## 2026-08-30 03:23 EEST — /root

- Intended: step 3 only—add PostgreSQL weekly-pattern compilation plus a PostgreSQL-only Alembic migration creating and backfilling the derived GiST-indexed schedule search table; SQLite migration remains a no-op and query/write paths remain unchanged.
- Areas: schedule compiler, Alembic migration, migration/compiler tests, and this progress log.
- Result (03:25 EEST): added deterministic minute-of-week multirange compilation and revision `20260830_0323`, which creates `refinement_schedule_index`, its GiST index, and backfills valid v1/legacy schedules on PostgreSQL; SQLite only advances the revision. No runtime write or query path uses the table yet.
- Verification: full `pytest` passed (164 tests), Ruff passed for Core/Web sources and tests, and `git diff --check` passed. PostgreSQL DDL was not applied to the configured database during this step. Follow-up: await review before transactional index maintenance.

## 2026-08-30 02:54 EEST — /root

- Intended: step 2 only—implement schedule v1 normalization and shared core occurrence expansion, retain legacy schedule read compatibility, and switch Web projection to the shared implementation; no database or query-index changes.
- Areas: `pino_core` schedule/model/refinement code, Web event projection, focused tests, and this progress log.
- Result (03:02 EEST): added typed v1 `occurrences`/weekly `recurrence` normalization, schedule-derived envelopes, legacy `opening_hours`/recurrence conversion, shared exact expansion including overnight sessions, and Web reuse with no coarse fallback after a schedule miss. Updated the refinement prompt to emit v1.
- Verification: full `pytest` passed (160 tests), Ruff passed for Core/Web sources and tests, and `git diff --check` passed. Follow-up: await review before adding the PostgreSQL-only derived index migration.

## 2026-08-29 18:56 EEST — /root

- Intended: step 1 only—document the reviewed schedule v1 JSON contract, `relevant_from`/`relevant_to` semantics, and planned PostgreSQL/SQLite query behavior; no code or schema changes.
- Areas: `docs/refinements.md` and this progress log.
- Result (18:57 EEST): documented versioned `occurrences`/weekly `recurrence` JSON, local-time and overnight rules, derived-envelope semantics, exact no-fallback behavior, and the planned PostgreSQL multirange/SQLite fallback split.
- Verification: reviewed the focused documentation diff and ran `git diff --check`; no code or schema changed. Follow-up: await review before implementing schedule normalization.

## 2026-08-28 02:01 EEST — /root

- Intended: independently review every `afisha_vilnius` golden fixture with the configured local LLM, then set each `ok` marker to match whether its `schedule` is supported by the entire message text.
- Areas: `packages/pino-core/tests/integration/golden/afisha_vilnius/` and this progress log.
- Result (02:06 EEST): three independent Codex Terra reviews covered all 100 fixtures; 90 are marked `ok: true` and 10 are marked `ok: false` for incomplete, unsupported, or malformed schedules. No marker is missing.
- Verification: parsed all YAML fixtures and counted markers (`100 files; 90 true; 10 false; 0 missing`); `git diff --check` passed. Follow-up: false fixtures retain their extracted schedules intentionally, as human-review failure examples.

## 2026-08-19

- Intended: retain exactly three `#список` fixtures in the generated Afisha corpus as ignored edge cases, always with `schedule: null`, while preserving coverage floors and total size 100.
- Result: regenerated 100 fixtures with exactly 3 `#список` items, all with null schedules; coverage remains 12 `каждый` and 86 weekday-stem items. Corpus now has 81 occurrence, 8 recurrence, and 11 null schedules.
- Verification: selector smoke test, Ruff, Python compilation, and automated validation of all 100 YAML files passed.

- Intended: extend the ad-hoc exporter to generate 100 deterministic `afisha-vilnius` golden fixtures under `packages/pino-core/tests/integration/golden/afisha_vilnius/`. Each fixture will contain source ID, URL, publication date, text, schedule, and non-date tags; schedules use correctly spelled `occurrence` or `recurrence`. Enforce at least 10% `каждый`, at least 10% Russian weekday stems, at most 5% `#список`, and no schedule for `#список`. No LLM or manual content review.
- Result: generated 100 fixtures with 12 `каждый`, 84 weekday-stem, 0 `#список`, 83 occurrence, 8 recurrence, and 9 null schedules. Selection only forced minimum coverage, then filled ordinary records chronologically. Date hashtags are excluded from `rest_tags`; list digests are coded to receive no schedule.
- Verification: deterministic schema/invariant pass over all 100 YAML files, script smoke tests and compilation, `pytest` (153 passed), Ruff, and `git diff --check`. Follow-up: stitch and manually verify expected schedules before treating the corpus as authoritative gold.

## 2026-08-18

- Intended: normalize Afisha date hashtags into ISO dates under provisional `schedule.matches.dates_refine`, using publication year; leave times and canonical records unchanged.
- Result: Russian date hashtags are now validated and normalized to ISO dates using `payload.posted_at_utc`'s year; times remain raw. Invalid dates are skipped and missing publication metadata produces an empty list.
- Verification: ruff, Python compilation, date-normalization/non-mutation smoke test, and `git diff --check` passed.

- Intended: add temporary Afisha source-token extraction to the ad-hoc DB YAML exporter. Touch only the script and this log; do not change models or schedule rules.
- Result: `afisha-vilnius` source exports now include provisional `schedule.matches` for raw date hashtags, time/range tokens, Russian weekday phrases, and hashtags; the same matches print to stderr. No model or schedule interpretation was added.
- Verification: `ruff check scripts/export_db_yaml.py`, `py_compile`, regex smoke test, and `git diff --check` passed. Follow-up: add recurrence/occurrence rules later.

- Intended: keep provisional schedule extraction outside the canonical source record in exporter output.
- Result: `schedule` is now a top-level export field; `record` remains unchanged.
- Verification: ruff, Python compilation, non-mutation smoke test, and `git diff --check` passed. No remaining risk beyond the intentionally provisional token-only shape.

## 2026-08-16

- Switched LLM-facing schedule weekdays from `MO/TU/...` abbreviations to full lowercase names, while normalizing back to internal day codes. Verification: core/refinement tests, full pytest, ruff.

## 2026-08-15

- Explained `recurrence` versus `opening_hours` in the refinement prompt. Verification: refinement tests, full pytest, ruff.
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
