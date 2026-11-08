# Task 1 — Core statistics read model

Read `AGENTS.md` and `docs/source-status-plan.md` first. Work only on this task,
using the reviewed preceding task as baseline. Keep changes uncommitted. Preserve
unrelated user files and `docs/progress.md`. No live DB, source fetches, deployment,
new dependencies, or unrelated refactors. Run tests appropriate to the changed
behavior, Ruff for Python, and `git diff --check`. Report exact results and every
new/untracked file needed by the implementation. Ask the supervisor about genuine
contract changes; make routine implementation choices independently.

Implement the approved metric contract using existing data only. Ingestion-time
activity is primary; use original `captured_at` with the explicit proxy label/basis
from the plan. Keep record counts, refinement coverage/backlog, and refinement output
item counts separate. No publication-time substitution or new ingestion timestamp.

Scope: `pino-core` reporting module/types, storage queries, focused tests. No API,
UI, migrations, pipeline writes, or CLI output changes. Preserve the publication
statistics command and its current meaning. Reuse date/bucketing code where useful
without importing CLI or forcing a general analytics abstraction.

Expose one typed report-building entry point with an injectable `as_of` clock,
weeks=1..52, and the explicit reporting timezone. Include source and city aggregates,
zero-filled ingestion weeks with current with-refinement/pending coverage, overall
and per-source backlog/oldest pending capture, refinement item counts by content kind,
latest captured/refined timestamps, and city-unassigned output buckets.
Return observed sources even when they have zero records in the requested weeks;
include registry cities with zero events. Never derive totals from capped event
queries or expanded occurrences. No per-source/city query loops or loading all raw
records into Python. Conditional SQL aggregates against precomputed UTC week bounds
are acceptable for SQLite/PostgreSQL portability. No index migration in this task;
report a measured need for one instead of expanding scope.

Acceptance tests: empty DB; records with multiple refinements; non-event results;
recurring/multiple-occurrence events counted once per event refinement; known and
missing city IDs; duplicate fetch preserving original capture; old sources with
zero recent counts; Monday boundary, DST, current partial week, future timestamps;
invalid week counts; no implicit system timezone. Explain capture-time import limits.
Also cover records with non-event/QC-unknown results (processed coverage, not backlog),
old backlog outside the weekly window, empty backlog/null age, refining an old record
without increasing this week's ingestion, and re-refinement replacing output without
double counting input records. Assert record and item count reconciliation separately.
No per-city raw ingestion/backlog when city is known only after refinement.
Use fixture SQLite; exercise PostgreSQL query construction or a disposable database
when available. Test that query count does not grow with source/city count. No SQL
snapshot tests that merely freeze implementation formatting.

## Completed handoff

Implemented by OpenCode `opencode/deepseek-v4.1-flash-free` from baseline `c1d81f8`,
reviewed and integrated into the main checkout without commits. Entry point:
`pino_core.stats.build_source_stats_report(store, weeks=8, as_of=..., reporting_timezone=...)`.
`stats.py` contains the typed core report; `storage.py` supplies six SQL aggregate
queries using one consistent snapshot. No raw-row scan into application memory or
source/city-dependent query loop. Existing publication stats remain unchanged.

Supervisor review found two issues, both repaired by DeepSeek: exact Monday-midnight
reports now allow an empty current week, and concurrent writes cannot make different
sections observe different database snapshots. A controlled SQLite WAL regression
proves the old inconsistency and the repaired behavior. PostgreSQL uses per-connection
REPEATABLE READ/read-only options; query compilation and connection use are tested,
but no live PostgreSQL instance was exercised. No migration or live DB access occurred.

Main-checkout validation: 336 Python tests pass, Ruff passes, diff checks pass. The
existing Starlette/httpx deprecation warning remains. No frontend checks were needed.
Luna coordinated initial automation; the supervisor completed final integration after
Luna reached its usage limit. No supervisor production-code repairs were required.

Files to include in the user commit:
- `packages/pino-core/src/pino_core/stats.py` (new)
- `packages/pino-core/tests/test_stats.py` (new)
- `packages/pino-core/src/pino_core/storage.py`
- `packages/pino-core/src/pino_core/__init__.py`

Keep the accepted plan/task documents with the project as appropriate; they are also
currently untracked. Original candidate and session evidence are retained in
`.pino/worktrees/source-status-task1-deepseek` and `.pino/source-status-task1/`.
Next checkpoint: user commit of this reviewed slice, then task 2 API work when asked.
