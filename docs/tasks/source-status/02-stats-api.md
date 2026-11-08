# Task 2 — Read-only statistics API

Read `AGENTS.md` and `docs/source-status-plan.md` first. Work only on this task,
using the reviewed preceding task as baseline. Keep changes uncommitted. Preserve
unrelated user files and `docs/progress.md`. No live DB, source fetches, deployment,
new dependencies, or unrelated refactors. Run tests appropriate to the changed
behavior, Ruff for Python, and `git diff --check`. Report exact results and every
new/untracked file needed by the implementation. Ask the supervisor about genuine
contract changes; make routine implementation choices independently.

Dependency: reviewed task 1. Add `GET /api/stats?weeks=8` using explicit HTTP models
for the plan's core report. Reuse existing FastAPI dependency/error handling style.
Keep `/api/health` and `/api/cities` unchanged. Do not construct adapters, fetch sources,
call CLI, initialize schemas, or infer source enablement from production config.

Scope: web API schemas/route/dependencies/thin service boundary and API tests. No UI,
pipeline, migration, or deployment work. Freeze a small documented response example
in `docs/source-status-plan.md` after implementation; actual code/tests are authoritative.
Return 422 for invalid weeks; preserve existing safe database-failure behavior.
Public data is strictly allowlisted: source names, aggregate counts, city metadata,
and relevant timestamps only. No raw config, URLs/settings, exceptions, session
paths, or source payloads. This endpoint is observational, not readiness.

Acceptance: response contract; 1/8/52-week requests; invalid bounds; empty DB;
source/city zero values; separate record/coverage/output counts and capture-time basis;
null backlog/last-refined timestamps; stable ordering; secret-like fixture values never appear;
no schema/data mutations or external calls; DB failure produces safe response.
Run API tests and affected core tests, then full Python suite and Ruff before handoff.
Stop for API contract review before task 3.
