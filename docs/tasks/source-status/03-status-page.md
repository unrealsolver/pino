# Task 3 — Useful statistics page

Read `AGENTS.md` and `docs/source-status-plan.md` first. Work only on this task,
using the reviewed preceding task as baseline. Keep changes uncommitted. Preserve
unrelated user files and `docs/progress.md`. No live DB, source fetches, deployment,
new dependencies, or unrelated refactors. Run tests appropriate to the changed
behavior, Ruff for Python, and `git diff --check`. Report exact results and every
new/untracked file needed by the implementation. Ask the supervisor about genuine
contract changes; make routine implementation choices independently.

Dependency: reviewed task 2 API. Add an explicit `/status` React route, reserve the
slug from city aliases, a small status link in the event header, and return/city
browse links. Preserve both existing city URL forms, entry redirects, query filters,
virtualization, and city metadata fetching behavior.

Scope: frontend API types/fetch, React Query hook/component, status route and tests;
small navigation additions. No backend or shared app-shell redesign. Use Mantine
components/tokens, CSS modules only when necessary. No chart/table dependencies.

Show ingestion/coverage cards first: raw records, records with refinement, pending
refinement, oldest pending capture. Follow with a separate refinement-output section
(current items by kind, refined event items, latest refinement result). Do not label
record coverage as success rate or output item counts as processed record counts.

Use an eight-week per-source ingestion table with current refined/pending coverage
for each captured cohort, plus per-source backlog outside the weekly window. Label
“First captured records”, the capture-time proxy/import caveat, partial current week,
and reporting timezone. Never suggest that cohort coverage is jobs completed that week
or historical queue size. City table counts are refined event items with browse links;
no inferred city-level raw ingestion/backlog. Explain event items are all time and not
cross-source deduplicated. Latest capture, latest refinement, and later last sync have
separate labels. Do not manufacture sync status before phase B.
Use absolute dates with zone and accessible descriptions; relative timestamps are
optional. Keep mobile tables usable, e.g. bounded horizontal scrolling.

Loading, error/retry, empty, background refresh and populated states are distinct.
Manual refresh; no automatic polling. API failure is never shown as all-zero data.
Test rendered real-router navigation, city route non-regression, response formatting,
zero/null values, mixed event/non-event/unknown outputs, backlog clearly separated
from output items, failed requests/retry, and a narrow-screen layout smoke check.
Run full frontend tests/build. Stop for manual UI review before schema work.
