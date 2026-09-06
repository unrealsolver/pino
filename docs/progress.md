# Progress Log

Short decision log, newest first. Detailed command history lives in git.

## 2026-09-06 03:28 EEST — /root

- Intended: show immediate source activity and failures in `pino check`, with an explicit final health summary.
- Areas: core pipeline progress callback, CLI rendering, focused tests, README.
- Result: added optional immutable CheckProgress events following the existing refinement callback pattern; CLI prints preparation, fetching, storing and immediate OK/FAILED outcomes. Final report explicitly names failures (or no failures/no sources), marks source rows and repeats error details as literal text. Existing fetch-failure exit behavior is preserved.
- Verification: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest packages/pino-core/tests/test_pipeline.py apps/pino-cli/tests/test_main.py -q` passed (32 tests), including assertions during fetch/storage to prove timely output, continuation, all-source failure, and literal error rendering. Ruff format/check and `git diff --check` passed. No live ingestion was run.
- Follow-up: none planned.

## 2026-09-06 03:04 EEST — /root

- Intended: fix Kaveikti listing extraction and raise clear extraction errors; isolate provider fetch failures in CheckPipeline with nullable result errors, preserving database error propagation and cursors.
- Areas: Kaveikti parser/fixtures/tests, core pipeline/tests, and this progress log.
- Result: Kaveikti parses current links, locations and images without microdata and raises ValueError for missing cards or wholly unparseable listings. Fetch exceptions become SourceCheckResult.error (type and message); other providers continue, failed cursors remain unchanged, and storage failures still propagate. CLI feedback deferred to the next step.
- Verification: focused pipeline/Kaveikti/CLI tests passed (34 tests); saved live listing parsed 21 records; Ruff format/check and git diff --check passed. Used UV_CACHE_DIR=/tmp/uv-cache after the default cache was read-only; no database ingestion was run.
- Follow-up: render source errors in the CLI separately. Zero-card Kaveikti pages currently raise because no reliable explicit empty-state marker has been verified; listings with some valid cards retain the existing skip behavior for malformed cards.

## 2026-09-04 00:33 EEST — /root

- Intended: add canonical nullable record publication time, backfill preserved Telegram timestamps, and add a zero-argument `pino sources stats` Rich grid covering eight Vilnius-aligned weeks by default.
- Areas: record/storage schema and migration, Telegram ingestion, source statistics contract/query and CLI, tests/documentation, and this progress log.
- Result (00:40 EEST): added nullable UTC `records.published_at`, indexed it, and added revision `0001` to backfill preserved Telegram `payload.posted_at_utc` values on PostgreSQL and SQLite. Telegram now writes the canonical field; duplicate ingestion hydrates it only when an existing row is null. Added `pino sources stats` with an eight-week default Rich grid, Vilnius-local Monday buckets, configured zero rows, and an all-time Unknown column. Refinement prompting and Afisha QC now read only the canonical field.
- Verification: focused storage/migration/refinement/evaluator/integration/CLI tests passed (92 tests); the full suite passed (200 tests); the SQLite backfill and PostgreSQL offline migration SQL were tested; Ruff lint passed repository-wide and formatting passed for all touched Python files; command/help rendering and `git diff --check` passed. No external database was migrated.
- Follow-up: Kaveikti and Vilnius Events remain Unknown because their current listing data has no trustworthy publication timestamp; retain `captured_at` for a later explicitly named first-seen metric rather than silently substituting it.
## 2026-09-03 23:49 EEST — /root

- Intended: remove the `pino digest` CLI command and its documentation while retaining the reusable core digest service and chat tool.
- Areas: CLI command surface, README/architecture/source documentation, focused CLI test coverage, and this progress log.
- Result (23:50 EEST): removed the top-level `pino digest` command, its CLI-only import, and command references from current README/architecture/source documentation. Retained `DigestService` and the `digest.create` chat tool as reusable core behavior.
- Verification: `pino --help` no longer lists `digest`; the full suite passed (196 tests); Ruff lint passed repository-wide and formatting passed for the touched Python file; `git diff --check` passed.
- Follow-up: none.

## 2026-09-03 04:34 EEST — /root

- Intended: make successful `pino refine` progress show a compact first-item representation using `relevant_from` and `summary`, while retaining the item count.
- Areas: refinement CLI progress rendering, focused test, and this progress log.
- Result (04:34 EEST): successful refinement progress retains its item count and now appends the first refinement as `<relevant_from or undated> — <summary or no summary>`, with the summary bounded to 100 characters.
- Verification: CLI tests passed (19 tests); the full suite passed (196 tests); Ruff lint passed repository-wide and formatting passed for the two touched Python files; `git diff --check` passed.
- Follow-up: none.

## 2026-09-03 04:23 EEST — /root

- Intended: move `chat` and `refine` model selection into provider-neutral LLM roles whose values are ordinary fully qualified profile references; remove role-named provider definitions and the old `llm.model` / `refinement.model` selectors.
- Areas: LLM/core configuration contracts, chat/refinement/eval wiring, local/example config, tests and documentation, and this progress log.
- Result (04:29 EEST): added provider-neutral `llm.roles.chat` and `llm.roles.refine`, each resolving an ordinary fully qualified profile reference. Chat and refinement now explicitly select their roles before client construction; schedule eval retains its explicit `--model` selection. Removed YAML `llm.model` / `refinement.model`, rejected those legacy selectors during file loading, removed role-named model definitions from local/example provider registries, and kept the runtime selection field out of serialized configuration.
- Verification: focused configuration/LLM/refinement/evaluator/CLI tests passed (97 tests); the full suite passed (196 tests); Ruff lint passed repository-wide and formatting passed for touched Python files; local/example configs resolved both roles and serialized without the runtime model field; `git diff --check` passed. No LLM was invoked.
- Follow-up: pause for review; add more roles only when another runtime path needs one.

## 2026-09-03 03:33 EEST — /root

- Intended: discard refinements rejected by deterministic QC and persist the shortest unambiguous proof so rejected records do not remain pending.
- Areas: refinement persistence boundary, focused tests and documentation, and this progress log; no database schema or migration.
- Result (03:35 EEST): QC-rejected generated items are discarded and replaced in storage by a minimal non-queryable refinement tombstone: `content_kind: unknown`, `refiner: qc:rejected`, and no summary, schedule, categories, or debug payload. Its existence removes the raw record from the pending queue. Non-QC model and transport errors remain unpersisted and retryable.
- Verification: focused refinement/storage/evaluator/CLI/QC tests passed (75 tests); the full suite passed (193 tests); Ruff lint passed repository-wide and formatting passed for touched Python files; `git diff --check` passed. No LLM was invoked.
- Follow-up: pause for review; add a separate rejection reason or retry workflow only when needed.

## 2026-09-03 02:50 EEST — /root

- Intended: add minimal immutable refinement-QC contracts and an Afisha Vilnius date-tag checker at the post-normalization/pre-persistence boundary; occurrence schedules use date-set containment and recurrence schedules only probe tagged dates.
- Areas: core QC contracts and refinement boundary, Afisha integration and configuration, schedule evaluation/CLI wiring, focused tests and documentation, and this progress log.
- Result (02:57 EEST): added immutable `QCFlag`/`QCReport` contracts and an injected post-normalization/pre-persistence check. Afisha Vilnius date tags use the publication year; explicit occurrences require tagged-date containment and warn on extra dates, while recurrence only probes each tagged date through the canonical schedule expander. QC errors block persistence and fail eval cases; warnings remain in-memory and are printed. Enabled the checker in example/local config without schema or migration changes.
- Verification: focused QC/refinement/evaluator/CLI tests passed (59 tests); the full suite passed (193 tests); Ruff lint passed for all packages/apps and formatting passed for touched Python files; both configs validated; all 87 accepted Afisha gold schedules passed deterministic QC; `git diff --check` passed. No LLM was invoked.
- Follow-up: pause for review before adding another QC dimension or source convention.

## 2026-09-03 00:58 EEST — /root

- Intended: prepare the accumulated schedule/refinement/evaluation work for a user commit by removing generated evaluation clutter, preventing legacy `out/` artifacts from reappearing, auditing the final diff, and running repository verification; do not commit.
- Areas: generated `out/` artifacts, `.gitignore`, accumulated tracked changes, and this progress log.
- Result (01:00 EEST): moved the untracked legacy `out/` evaluation tree (2,536 files, 12 MB) to recoverable `/tmp/pino-eval-out-20260903`, ignored future `/out/` artifacts, synchronized the corpus-count test with the three multi-event exclusions, and aligned the example MiniMax/GPT schedule profiles with the documented aliases and accepted sampling settings. All remaining worktree changes are substantive source, documentation, tests, or deliberate golden corrections; no commit was created.
- Verification: full suite passed (185 tests); Ruff lint passed repository-wide; Ruff formatting passed for all changed Python files; `config.example.yaml` loaded and both evaluation profiles resolved with expected settings; `git diff --check` passed.
- Follow-up: user commit; ignored `.pino/` evaluation history remains available locally, and the moved legacy artifacts can be deleted from `/tmp` when no longer needed.

## 2026-09-03 00:08 EEST — /root

- Intended: add a local schedule-evaluation profile for the installed `ornith-1.5:35b`, using author-recommended general-task sampling and a no-reasoning baseline.
- Areas: local `config.yaml` and this progress log.
- Result (00:09 EEST): added `ollama:schedule-ornith-1-5-35b` for the exact installed model tag with temperature `0.6`, top-p `0.95`, 32K context, a 2K output cap, and thinking disabled for the initial comparable extraction baseline. No generic `top_k` option was added.
- Verification: the profile resolved with all expected typed values; focused config tests passed (19 tests); `git diff --check` passed; the installed Ollama metadata was inspected without invoking the model.
- Follow-up: run a small smoke evaluation, then the same corpus used for the other local profiles if its output contract is sound.

## 2026-09-02 23:56 EEST — /root

- Intended: make schedule evaluation provider-neutral through `pino-llm`, preserve existing usage accounting and optional Ollama diagnostics, and add a MiniMax M3 evaluation profile using manufacturer-recommended sampling.
- Areas: LLM client factory/timeouts and normalized call diagnostics, schedule evaluator and CLI, local config, documentation, focused tests, and this progress log.
- Result (2026-09-03 00:01 EEST): schedule evaluation now resolves every registered provider through `build_llm_client`; the shared factory accepts an optional timeout, OpenAI-compatible reasoning is exposed when returned, and existing normalized usage is captured for hosted output-token totals while provider-only generation throughput remains optional. Removed Ollama-only CLI/core guards, generalized help/docs, and added local `minimax:schedule-m3` with MiniMax's recommended temperature `1` and top-p `0.95`. No schema or generic parameter bag was added.
- Verification: full test suite passed (185 tests); Ruff lint passed repository-wide and formatting passed for touched Python files; `minimax:schedule-m3` resolved with expected values; provider-neutral CLI help rendered; `git diff --check` passed. No external model was invoked.
- Follow-up: run a small MiniMax smoke eval with an explicit timeout, then inspect `evaluation.schedule` usage before committing to the full corpus.

## 2026-09-02 19:59 EEST — /root

- Intended: add isolated schedule-eval profiles for GPT-OSS 20B medium reasoning and Muse Glimmer with reasoning disabled and low reasoning; inspect the latest GPT-OSS/Qwen failure modes without changing prompts or tests.
- Areas: local `config.yaml`, latest evaluation artifacts, and this progress log.
- Result (20:01 EEST): added `ollama:schedule-gpt-oss-20b-medium`, `ollama:schedule-muse-glimmer`, and `ollama:schedule-muse-glimmer-low` with comparable sampling, 32K context, and 2K generation limits; removed Qwen's dead duplicate `think: false` key. Reviewed the latest paired GPT-OSS/Qwen failures and identified multi-event fixture contamination, two canonical-representation/prompt artifacts, and substantive date/boundary errors. No prompt, fixture, schema, or committed test was changed.
- Verification: loaded `config.yaml` and resolved all three profiles with expected typed values; confirmed the installed Muse Glimmer advertises thinking and official Ollama documentation supports controllable reasoning levels; config tests passed (19 tests); `git diff --check` passed. No model was invoked.
- Follow-up: run the three new profiles; compare GPT medium against low primarily on recurrence boundaries `092` and `099`, and keep multi-event cases `004`, `007`, and `025` out of model-quality conclusions.

## 2026-09-02 16:37 EEST — /root

- Intended: persist token usage from schedule-evaluation LLM calls through the existing configured usage store, without changing the usage schema or evaluation report format.
- Areas: schedule evaluator wiring, CLI integration, usage documentation, focused tests, and this progress log.
- Result (16:41 EEST): schedule evaluation now records every completed Ollama request in the configured `llm_usage_events` store and labels it `evaluation.schedule`, keeping benchmark traffic separate from production `refinement.extract`. Provider failures without returned usage remain unrecorded; report artifacts and schema are unchanged.
- Verification: CLI wiring test persisted and read back an `evaluation.schedule` event; evaluator tests verify the operation label; full test suite passed (183 tests); Ruff lint and formatting checks passed for touched Python files; `git diff --check` passed. No model was invoked.
- Follow-up: existing eval runs are not backfilled; run a new evaluation and inspect it with `pino usage summary --group-by operation` or `pino usage recent`.

## 2026-09-02 15:49 EEST — /root

- Intended: add comparable local schedule-eval profiles for `qwen3.8:27b` and `gpt-oss:20b`, use explicit model-based aliases, and remove the duplicate Nemotron thinking key.
- Areas: local `config.yaml` and this progress log.
- Result (15:52 EEST): added `ollama:schedule-qwen3-8-27b`, renamed the GPT-OSS evaluation profile to `ollama:schedule-gpt-oss-20b`, aligned both with the Nemotron evaluation limits, and removed Nemotron's conflicting duplicate `think` key. No model was invoked.
- Verification: loaded `config.yaml` and resolved all three Ollama profiles with the expected models and parameters; config tests passed (19 tests); `git diff --check` passed.
- Follow-up: run the same schedule-eval corpus against the three explicit aliases for comparison.

## 2026-09-02 15:25 EEST — /root

- Intended: make refinement LLM output a single direct item or `{"error": "..."}`, remove `source_text` from canonical schedules, and update prompt/docs/tests while retaining list-based storage APIs and `item_index = 0`; do not change golden fixture `045.yaml`.
- Areas: refinement service and prompt, schedule model, documentation, CLI/evaluator fixtures, focused tests, and this progress log.
- Result (15:32 EEST): refinement now accepts exactly one direct item object or a one-field model error, reports model error reasons, and wraps successful output as one internal refinement with index zero. Updated the prompt for atomic input, non-event handling, upstream splitting, and the error alternative. Removed `source_text` from schedule validation, serialization, prompt examples, documentation, and test fixtures. Retained list-based persistence and the database schema; did not modify `045.yaml`.
- Verification: focused refinement/schedule/evaluator/CLI tests passed (59 tests), the full repository suite passed (183 tests) before final mechanical formatting, focused tests passed again afterward, Ruff lint and format checks passed for all touched Python files, stale contract strings were absent, and `git diff --check` passed. No model was invoked.
- Follow-up: run a fresh schedule eval; multi-event fixtures should now return explicit model errors and remain candidates for an upstream splitter benchmark.

## 2026-09-02 05:10 EEST — /root

- Intended: remove `relevant_from`/`relevant_to` from the LLM refinement contract, derive them only from normalized schedules, and remove legacy coalescing based on model-provided relevance timestamps while retaining database/search fields.
- Areas: refinement parser and prompt, focused refinement/evaluator tests, and this progress log.
- Result (05:13 EEST): removed relevance fields from the rendered LLM response shape and raw-item ingestion, made schedule the sole LLM event-timing field, and added the at-least-one-item/non-event rule. Persisted relevance fields remain unchanged and derive from normalized schedules. Removed the legacy weekly coalescer and its timestamp-based helpers; unexpected legacy relevance keys are now ignored. Updated focused tests without changing golden fixtures or database schema.
- Verification: focused refinement/evaluator tests passed (30 tests), full repository tests passed (183 tests), Ruff lint and format checks passed for touched Python files, and `git diff --check` passed. No model was invoked.
- Follow-up: run a fresh schedule eval and compare schedule omissions, null-item handling, recurrence accuracy, and invalid output against the 68/90 run.

## 2026-09-02 03:12 EEST — /root

- Intended: generalize the refinement schedule prompt around event identity and source-supported temporal semantics; remove fixture-specific date/season examples and tighten occurrence, recurrence, and boundary selection without changing the model or tests.
- Areas: refinement system prompt and this progress log.
- Result (03:13 EEST): replaced fixture-specific summer/Vilnius and concrete date examples with generic event identity, event-timing evidence, session separation, weekly representability, source-supported boundary, publication-date anchoring, and schema-integrity rules. Non-weekly patterns are no longer approximated as weekly, and contextual availability is not treated as an event occurrence. No test or golden fixture was edited.
- Verification: focused refinement tests passed (20 tests), Ruff passed for the changed Python file, and `git diff --check` passed. No model was invoked.
- Follow-up: run a fresh schedule eval and compare total accuracy, recurrence accuracy, invalid responses, and omitted-year behavior against the 73/90 run.

## 2026-09-02 02:52 EEST — /root

- Intended: make `publication_date` the authoritative omitted-year anchor in the refinement prompt, including an explicit 2026 example and final year-resolution audit; do not change tests or golden fixtures.
- Areas: refinement system prompt and this progress log.
- Result (02:53 EEST): strengthened rule 6 so omitted years default to `publication_date` and cannot be selected from model time, external knowledge, URLs, or weekday agreement; retained the time-only guard, added a concrete June 2026 example, and extended the final audit. No test or golden fixture was edited.
- Verification: focused refinement tests passed (20 tests), Ruff passed for the changed Python file, and `git diff --check` passed. The initial focused run exposed a removed prompt-contract phrase; the prompt retained that phrase and the rerun passed. No model was invoked.
- Follow-up: run a fresh schedule eval and compare both total accuracy and the count of responses containing 2024 occurrence years.

## 2026-09-02 02:44 EEST — /root

- Intended: preserve the existing refinement schedule instructions as comments and replace them with an ordered extraction procedure plus a final output audit; do not change golden fixtures or tests.
- Areas: refinement system prompt and this progress log.
- Result (02:45 EEST): retained the prior temporal prompt block as source comments and replaced its rendered text with an ordered schedule decision procedure covering event identity, mandatory schedules, occurrence/recurrence choice, recurrence boundaries, publication-date limits, non-invention, schema placement, timezone handling, and a final JSON/invariant audit. No test or golden fixture was edited.
- Verification: focused refinement tests passed (20 tests), Ruff passed for the changed Python file, and `git diff --check` passed. No model was invoked.
- Follow-up: rerun the schedule evaluator to measure the prompt's accuracy impact; fixture `045.yaml` still contains the user-owned duplicate `start` key and was deliberately left untouched.

## 2026-09-01 23:38 EEST — /root

- Intended: compact schedule-eval YAML case entries to name, error/no-error, and wall duration only; retain aggregate metrics, raw artifacts, and immediate CLI diagnostics.
- Areas: schedule evaluator live summary, tests, README, and this progress log.
- Result (23:39 EEST): live YAML case rows now contain only `name`, `error`, and wall-clock `duration_ms`. Passing cases store `error: null`, mismatches store `error: mismatch`, and provider/parser failures retain their message. Removed duplicated schedules, statuses, token telemetry, and artifact paths from case rows; aggregate metrics and fixture-named response/reasoning files remain unchanged.
- Verification: focused schedule-eval/CLI tests passed (29 tests), full `pytest` passed (183 tests), Ruff passed for all packages/apps, and `git diff --check` passed. No model was invoked. Follow-up: run a fresh eval after review to inspect the compact live summary.

## 2026-09-01 23:13 EEST — /root

- Intended: derive schedule-eval generation throughput from Ollama-native token count and generation duration; persist per-case output tokens/duration/tok-s and a weighted aggregate, and show it in the comparison CLI.
- Areas: Ollama response telemetry, schedule evaluator/report YAML, CLI output, tests, README, and this progress log.
- Result (23:15 EEST): Ollama now exposes its latest native `eval_count` and `eval_duration` as output-token, generation-duration, and derived tok/s telemetry. Schedule eval persists those three values per case and records total output tokens, summed generation duration, and duration-weighted tok/s in the live summary; the comparison table shows aggregate generation throughput. Wall-clock latency remains separate.
- Verification: focused telemetry/evaluator/CLI tests passed (38 tests), full `pytest` passed (183 tests), Ruff passed for all packages/apps, and `git diff --check` passed. No model was invoked. Follow-up: existing reports naturally lack the new fields; run a fresh eval after review.

## 2026-09-01 23:08 EEST — /root

- Intended: render the researched Nemotron sampling, thinking, context, and output settings into the local schedule profile; do not change evaluator timeout.
- Areas: local `config.yaml` and this progress log.
- Result (23:09 EEST): updated `ollama:schedule-nemotron` to temperature `1`, top-p `0.95`, thinking enabled, 32K context, and a 4K output cap. Evaluator timeout was not changed.
- Verification: loaded `config.yaml` and resolved all five settings with the expected types and values; `git diff --check` passed. No model was invoked. Follow-up: review and commit with the surrounding model-registry work.

## 2026-09-01 04:16 EEST — /root

- Intended: add a local Ollama schedule-evaluation profile for `nemotron-3.5-lightning` without changing model-registry behavior or invoking the model.
- Areas: local `config.yaml` and this progress log.
- Result (04:16 EEST): added local profile `ollama:schedule-nemotron`, resolving to `nemotron-3.5-lightning` with temperature `0`; no committed example or runtime behavior changed.
- Verification: loaded `config.yaml` and resolved the new profile to Ollama with the expected model and parameters; `git diff --check` passed. No model was invoked. Follow-up: review and commit with the surrounding model-registry work.

## 2026-09-01 04:09 EEST — /root

- Intended: reshape `llm.models` so definitions use plain names inside provider namespaces while references remain fully qualified as `provider:name`; remove redundant `provider` fields from definitions without changing runtime options.
- Areas: LLM configuration/resolution, application configs, tests, documentation, and this progress log.
- Result (04:12 EEST): model definitions now use plain keys beneath provider namespaces (`llm.models.<provider>.<name>`) and omit redundant `provider` fields. Selectors use strict fully qualified `provider:name` references; provider/name parsing, lookup, plain-name validation, and provider-specific option validation remain typed. Updated local/example configs, CLI wording, documentation, and tests.
- Verification: full `pytest` passed (183 tests), Ruff passed for all packages/apps, local and example configs loaded with resolved provider profiles, CLI help rendered, redundant definition-level provider fields were absent, and `git diff --check` passed. No model was invoked. Follow-up: review and commit.

## 2026-09-01 02:37 EEST — /root

- Intended: replace provider-owned aliases and `default_provider` with one typed `llm.models` profile registry; require strict opaque aliases at Pino entry points, apply profile inference settings, expose resolved eval settings, and document the configuration contract.
- Areas: LLM configuration/providers, refinement and schedule-eval integration, application configs/CLI, tests, README, and this progress log.
- Result (02:44 EEST): added a strict typed `llm.models` registry and removed `default_provider`, provider-owned aliases/defaults, global inference settings, and the unused Echo provider flag. Chat/refinement/eval now select registered aliases; profiles own provider model, temperature/top-p, and typed Ollama `think`/`num_ctx`/`num_predict` settings. Eval rejects non-Ollama profiles and records alias plus resolved settings in live YAML. Updated committed example, local `config.yaml`, CLI diagnostics/help, and documentation.
- Verification: full `pytest` passed (182 tests), Ruff passed for all packages/apps, both configs loaded with their intended chat/refinement aliases, CLI help rendered, stale config fields were absent, and `git diff --check` passed. No model was invoked. Follow-up: review and commit; external/local override configs using the old shape must be updated.

## 2026-09-01 01:33 EEST — /root

- Intended: persist Ollama reasoning for every schedule-eval case as an immediate, separate artifact referenced by the live YAML summary; do not add inference-parameter controls yet.
- Areas: schedule evaluator artifacts/progress, CLI diagnostics/tests, README, and this progress log.
- Result (01:34 EEST): reasoning returned through Ollama's separate `message.thinking` field is now written immediately to `reasoning/<fixture>.txt` for passing and failing cases, referenced from `summary.yaml`, and shown as an artifact path for CLI failures. Cases without reasoning record `null`.
- Verification: full `pytest` passed (179 tests), Ruff and `git diff --check` passed. No Ollama model was invoked. Follow-up: decide separately whether resolved inference parameters belong in typed Pino config; no generic `--params` or think control was added.

## 2026-08-31 04:42 EEST — /root

- Intended: remove all schedule-eval response caching and cache controls; produce fresh, incrementally visible, test-style diagnostics with readable expected/actual values and responses for every case.
- Areas: schedule evaluator/report model, CLI output/options/tests, README, and this progress log.
- Result (05:02 EEST): schedule evals always call Ollama afresh and create a timestamped run directory. A readable `summary.yaml` is created before the first request and updated after every case; every available response, including passes, is written immediately to a separate `.json`/`.txt` file. Failure expected/actual/error details and each model's completion summary print immediately. Removed `report.json`, `--refresh`, `--cache-dir`, and all cache counters; added `--output-dir`.
- Verification: full `pytest` passed (179 tests), Ruff, CLI help, and `git diff --check` passed. No Ollama model was invoked by this session. Follow-up: pre-existing `out/` eval artifacts and old cache artifacts are ignored and were not modified or deleted.

## 2026-08-31 03:38 EEST — /root

- Intended: add per-model total/min/max/p50 evaluation timing statistics and an evaluator-only `--timeout` option defaulting to 15 seconds; preserve production Ollama timeout behavior.
- Areas: Ollama client timeout injection, schedule evaluator summaries/reports, CLI/tests, README, and this progress log.
- Result (03:41 EEST): model summaries and JSON reports now include total/min/p50/mean/max request durations; `pino eval schedules --timeout` defaults to 15 seconds. Timed-out/provider-error cases are recorded as invalid and evaluation continues, while normal Ollama calls retain their 120-second default.
- Verification: full `pytest` passed (178 tests), Ruff, CLI help, and `git diff --check` passed. No Ollama model was invoked. Follow-up: none beyond review and the intended model comparison.

## 2026-08-31 03:34 EEST — /root

- Intended: make long schedule-model evaluations visibly progress per model and fixture, including pass/invalid/cache/elapsed counters, without changing evaluation semantics.
- Areas: schedule evaluator callback, CLI rendering/tests, README guidance, and this progress log.
- Result (03:36 EEST): each model now announces its fixture count and emits one durable line after every fixture with status plus cumulative exact, invalid, cache-hit, and elapsed-time counters.
- Verification: full `pytest` passed (176 tests), Ruff and `git diff --check` passed. No Ollama model was invoked. Follow-up: none beyond running the intended model comparison after review.

## 2026-08-31 02:01 EEST — /root

- Intended: add a schedule-only Ollama model evaluation over valid Afisha Vilnius golden fixtures, reusing the production refinement prompt/parser, canonicalizing legacy gold schedules, caching raw responses, and reporting exact accuracy/latency by schedule kind; do not run models implicitly.
- Areas: Core evaluation module/tests, `pino eval schedules` CLI/tests, usage documentation, and this progress log.
- Result (02:08 EEST): added `pino eval schedules` with explicit repeated `--model`, reviewed-fixture validation (90 scored, 10 excluded), canonical exact schedule scoring, per-kind/invalid/latency summaries, and prompt-keyed raw-response/report caching.
- Verification: full `pytest` passed (176 tests), Ruff and `git diff --check` passed, and CLI help rendered. No Ollama model was invoked. Follow-up: run a small `--limit` comparison, then the full corpus for promising models; repository-wide format check still identifies pre-existing drift in 20 unrelated files.

## 2026-08-31 01:54 EEST — /root

- Intended: allow reset bootstrap to retain existing `active_memory` and `llm_usage_events` tables by using `CREATE TABLE IF NOT EXISTS` for only those two initial-schema operations; keep all other tables strict.
- Areas: revision `0000` DDL, SQLite/PostgreSQL migration assertions, and this progress log.
- Result (01:55 EEST): revision `0000` now emits `CREATE TABLE IF NOT EXISTS` for `active_memory` and `llm_usage_events` only. Other tables still fail on an incomplete reset, and retained rows survive bootstrap unchanged.
- Verification: full `pytest` passed (168 tests), Ruff passed for all packages/apps, SQLite preservation and PostgreSQL offline `IF NOT EXISTS` DDL are covered, and `git diff --check` passed. Follow-up: retained tables must already have the current column shape.

## 2026-08-31 01:28 EEST — /root

- Intended: finish schema lifecycle cleanup—make `DatabaseStore.init_schema()` apply Alembic revision `0000` on its existing engine, remove `metadata.create_all()` and the manual SQLite repair, update storage documentation, and verify SQLite plus PostgreSQL-oriented bootstrap paths.
- Areas: Core database/bootstrap helpers, storage tests, README/tech-stack guidance, and this progress log.
- Result (01:30 EEST): `init_schema()` now upgrades revision `0000` through Alembic on the store's existing engine, including in-memory SQLite; removed runtime `create_all()` and the PRAGMA-based legacy repair. Updated storage documentation to describe the shared SQLite/PostgreSQL lifecycle.
- Verification: full `pytest` passed (167 tests), Ruff passed for all packages/apps, no legacy schema-repair references remain, and `git diff --check` passed. PostgreSQL bootstrap is covered by engine-delegation and offline DDL tests but not a live server. Follow-up: drop old databases, create an empty target, and run acceptance testing.

## 2026-08-31 00:32 EEST — /root

- Intended: finalize the reset migration history as a single revision literally named `0000`, retaining Alembic for deterministic current-schema creation and future evolution; no schema or runtime-bootstrap change.
- Areas: initial migration identity/filename, migration assertions/history, prior squash log wording, and this progress log.
- Result (00:33 EEST): the only migration is now `versions/0000_initial_schema.py` with revision `0000`; it remains the complete SQLite/PostgreSQL baseline and has no compatibility history. Schema behavior is unchanged from the reviewed squash.
- Verification: full `pytest` passed (166 tests), Ruff passed for all packages/apps, Alembic reports `0000` as both base and head, and `git diff --check` passed. Follow-up: await review before making runtime bootstrap migration-backed.

## 2026-08-31 00:28 EEST — /root

- Intended: reset-oriented schema cleanup—replace the compatibility migration chain with one fresh current-schema baseline for SQLite/PostgreSQL, including the PostgreSQL-only schedule index; discard the uncommitted reconciliation migration, but leave runtime bootstrap unchanged until the next review point.
- Areas: Alembic versions/history, fresh-schema migration tests, superseded phase-2 log outcome, and this progress log.
- Result (00:30 EEST): replaced all historical revisions with one current-schema baseline, which creates the complete portable schema and conditionally creates the PostgreSQL multirange table plus GiST index. Removed legacy backfills and compatibility-only tests. Runtime `init_schema` is still unchanged.
- Verification: full `pytest` passed (166 tests), Ruff passed for all packages/apps, SQLite migration output matches every portable metadata column, offline PostgreSQL DDL contains `INT4MULTIRANGE` and `USING gist`, migration history has one revision, and `git diff --check` passed. Follow-up: await review before migration-backed runtime bootstrap.

## 2026-08-30 23:47 EEST — /root

- Intended: schema-lifecycle cleanup phase 2—add a cross-database Alembic reconciliation for legacy `records.external_id`/`fingerprint` storage and its unique index; keep the manual SQLite repair until migration-backed runtime bootstrap lands in phase 3.
- Areas: new head migration, legacy SQLite/PostgreSQL-compatible backfill behavior, migration tests, and this progress log.
- Result (23:50 EEST): added head revision `20260830_2347`, which adds missing record-identity columns, deterministically backfills fingerprints, preserves duplicate legacy rows with stable fallback identities, enforces non-null fingerprints, and ensures uniqueness using portable Alembic/SQLAlchemy operations. The manual SQLite repair remains active until phase 3.
- Verification: full `pytest` passed (170 tests), Ruff passed for all packages/apps, the migration graph resolves to the new head, and `git diff --check` passed. The prior-head upgrade path is covered on SQLite; live PostgreSQL execution remains untested. Follow-up: await review before migration-backed `init_schema` and manual-repair removal.
- Superseded (2026-08-31 00:28 EEST): this uncommitted reconciliation was discarded after the user confirmed all databases will be recreated from scratch.

## 2026-08-30 22:24 EEST — /root

- Intended: schema-lifecycle cleanup step 1 only—add an idempotent portable Alembic baseline so an empty SQLite or PostgreSQL database can enter the existing migration chain; do not change runtime `init_schema` behavior yet.
- Areas: migration baseline/ancestry, fresh-database migration tests, and this progress log.
- Result (22:26 EEST): added base revision `20260610_0000` for the five portable pre-schedule tables and linked the existing migration chain to it. The baseline creates missing tables but tolerates pre-Alembic tables, while later revisions still add schedule and usage storage. Runtime `init_schema` is unchanged.
- Verification: full `pytest` passed (169 tests), Ruff passed for all packages/apps, migration history resolves as one base-to-head chain, and `git diff --check` passed. PostgreSQL execution remains untested without a live server. Follow-up: await review before legacy-column reconciliation.
- Superseded (2026-08-31 00:28 EEST): replaced by the current-schema baseline after database-reset compatibility became unnecessary.

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
