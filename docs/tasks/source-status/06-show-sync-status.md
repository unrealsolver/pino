# Task 6 — Expose genuine last-sync information

Read `AGENTS.md` and `docs/source-status-plan.md` first. Work only on this task,
using the reviewed preceding task as baseline. Keep changes uncommitted. Preserve
unrelated user files and `docs/progress.md`. No live DB, source fetches, deployment,
new dependencies, or unrelated refactors. Run tests appropriate to the changed
behavior, Ruff for Python, and `git diff --check`. Report exact results and every
new/untracked file needed by the implementation. Ask the supervisor about genuine
contract changes; make routine implementation choices independently.

Dependency: reviewed task 5. Extend the existing stats report/API additively and
finish the status UI. Union source names from records and sync runs so first-attempt
failures/zero-result sources appear. Add a read-only `uv run pino sources health`
command using the same core interpretation, not a second set of status rules.
The existing `sources stats` publication-grid behavior stays unchanged.

For each source show last recorded attempt/outcome and last successful completion;
use the safe states and UTC timestamps defined in the plan. No recorded attempt is
unknown, unfinished is not automatically running/failed, success with zero inserted
is still success. Avoid red/green claims about current availability or guessed sync
cadence. Show coarse safe failure stage if useful, never raw exceptions. Keep sync
(fetched/stored) distinct from downstream LLM refinement and media-upload freshness. Preserve the
ingestion/refinement metrics from phase A; a successful sync can add to refinement
backlog and does not mean that newly ingested records have been refined.

Scope: core reporting read path, API models/tests, CLI health display/tests, frontend
status rendering/tests. No new migration, adapter redesign, background jobs, or live
DB actions. The CLI command must require existing schema, not call the auto-migrating
CLI `get_store` helper. It performs no writes, source checks, or refinement calls.

Acceptance: matching API/CLI interpretation; failed-after-success; never recorded;
unfinished; zero-new success; source absent from records; concurrent-attempt order;
public response excludes secret-like raw errors. Test UI timestamp/null/error cases,
existing city behavior, and correct source totals. Full Python and frontend checks,
Ruff/build/diff check. Provide release instructions and live smoke checklist; actual
shared migration, deploy, or source fetch requires explicit user authorization.
