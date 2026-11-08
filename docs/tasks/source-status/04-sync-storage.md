# Task 4 — Persist source sync attempts

Read `AGENTS.md` and `docs/source-status-plan.md` first. Work only on this task,
using the reviewed preceding task as baseline. Keep changes uncommitted. Preserve
unrelated user files and `docs/progress.md`. No live DB, source fetches, deployment,
new dependencies, or unrelated refactors. Run tests appropriate to the changed
behavior, Ruff for Python, and `git diff --check`. Report exact results and every
new/untracked file needed by the implementation. Ask the supervisor about genuine
contract changes; make routine implementation choices independently.

Dependency: phase A accepted. Add an additive migration and storage operations for
one `source_sync_runs` row per pipeline attempt, as defined in the plan. The row is
created at start and completed once; completed observations are not overwritten by
later runs. Persist no raw errors/settings. Index queries for latest attempt and
last completed success per source. Update schema revision expectations as required.

Scope: core schema, migration, typed storage interface and tests only. No pipeline,
CLI, API, UI, actual migrations against user DB, or historical backfill. Operations:
start attempt; complete success/failure with counts and safe stage; query latest
attempt and latest successful completion independently, including sources with no
records. Use aware UTC timestamps and injected clock/explicit timestamps in tests.

Acceptance: migration from previous revision with existing data unchanged; empty
new DB; success/zero-result/failure; failed-after-success; unfinished row; partial
counts; overlapping attempts finishing out of order; stable ties; attempted-source
without records; repeated completion does not corrupt a terminal row; SQLite and
PostgreSQL-compatible schema/queries. Migration/check commands use only disposable
DBs. No table creation on report reads. Full Python checks before handoff.
Stop for migration review and a user commit; do not apply it to the shared DB.
