# Task 5 — Instrument ingestion without changing its semantics

Read `AGENTS.md` and `docs/source-status-plan.md` first. Work only on this task,
using the reviewed preceding task as baseline. Keep changes uncommitted. Preserve
unrelated user files and `docs/progress.md`. No live DB, source fetches, deployment,
new dependencies, or unrelated refactors. Run tests appropriate to the changed
behavior, Ruff for Python, and `git diff --check`. Report exact results and every
new/untracked file needed by the implementation. Ask the supervisor about genuine
contract changes; make routine implementation choices independently.

Dependency: reviewed task 4. Wire durable attempts into `CheckPipeline`, starting
before fetch and recording terminal outcomes for required fetch/store/cursor work.
Reuse existing SourceCheckResult counts/meaning. Do not duplicate CLI-only tracking,
change adapter APIs, or refactor all source construction.

Scope: core pipeline and its tests; narrow storage corrections only if needed.
Preserve current behavior: fetch failures report and continue; storage/cursor
failures propagate; cursors advance only after returned records are stored;
non-fatal media-fetch warnings remain non-fatal. Partial commits are real: report
partial inserted/duplicate counts rather than pretending an entire batch rolled back.
Important existing ordering: `add_record` commits before media enrichment/image
persistence and before the current loop increments inserted counters. A subsequent
media DB-write failure must not hide that already committed insert in the recorded
partial count. Test that exact case without changing non-fatal download behavior.
Completion/storage failures must not falsely claim saved status or mask the original
error; logging may explain telemetry failure without recursion. Do not add retries.

Successful empty and duplicate-only syncs advance last successful completion. Failed
runs do not erase previous successes. A killed/interrupted run can remain unfinished;
no heartbeat or invented timeout policy. Adapter-construction/config-load errors
before pipeline startup remain explicit CLI errors, not fake per-source attempts.

Use fake adapters and disposable stores. Cover normal/cursor/zero/duplicate runs,
fetch failure followed by a successful next source, partial storage failure, cursor
failure, non-fatal media failure, and telemetry-write failure. Preserve CLI progress
and totals. Run pipeline/CLI/core tests and full Python suite/Ruff. Do not execute a
real check or migrate the shared DB. Stop for failure-semantics review.
