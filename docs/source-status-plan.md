# Sources, cities, and data status

Status: plan accepted in principle, updated 2026-10-27 to prioritize ingestion and
refinement metrics. Task 1 was explicitly authorized and is implemented/reviewed
in the main checkout, uncommitted. Tasks 2–6 have not started; this document does
not authorize shared-database changes or deployment. The existing Python + React SPA
stack remains. Implementation worker: OpenCode `opencode/deepseek-v4.1-flash-free`;
Luna coordinates automation; supervisor reviews scope, correctness, and acceptance.

## Product

One read-only `/status` page with separate ingestion, refinement/backlog, and city
sections. Ingestion-time activity and refinement coverage take priority over source
publication dates. Start with information already stored; add genuine sync outcomes
in a second phase. No charts library, management controls, job scheduler, live
source probes, or dashboard framework. A small Refresh action is sufficient.

Proposed default: public page exposing only deliberately selected fields. No source
settings, credentials, filesystem/session paths, raw exception messages, payloads,
or diagnostic refinement output. Private/operator-only access would be a separate
access-control decision before publishing this endpoint.

## What exists

- `uv run pino sources stats --weeks 8` prints publication-week record counts.
  `print_source_stats` lives in `apps/pino-cli/src/pino_cli/main.py` and calls
  `DatabaseStore.summarize_source_publications`.
- `uv run pino check` prints per-source success/failure and fetched/inserted/duplicate
  counts. `CheckPipeline` returns those results but does not persist them.
- `records.captured_at` is the capture timestamp retained on the first insert;
  duplicate insertion does not advance it. It is not a database insertion audit:
  imported/static records can supply their own historical capture time.
- `source_cursors.updated_at` only describes cursor persistence. It must not be
  presented as last sync. Neither latest publication nor latest capture proves a
  successful zero-result sync.
- Cities come from `pino_core.cities`; `/api/cities` is already the routing registry.
- Refinements are the current `(record_id, item_index)` results. A raw record may
  yield multiple events; an event may produce multiple displayed occurrences.
- Production reads the same DB as workstation ingestion, but does not run ingestion.
  Production source configuration must not be assumed identical to the workstation.

## Metric contract

User decision: ingestion-time activity is the primary weekly metric; ingestion and
refinement are separate stages and must never share an ambiguous “added/events” count.
Source publication statistics remain secondary and the existing CLI keeps its current
publication-date meaning. No publication-week series is needed on the initial page.

For phase A, use retained `records.captured_at` as the existing ingestion-time proxy.
Expose `ingestion_time_basis: "captured_at"` in the report; label the weekly series
“First captured records” and explain it represents the original stored capture time.
A duplicate fetch does not count again. Imported records may have a historical capture
time; do not claim exact DB insertion dates. Exact `ingested_at` tracking, if wanted
later, requires a separate additive migration and an honest unknown/estimated policy
for historical rows; do not silently add it or fabricate historical insertion times.

### Ingestion and refinement coverage (record counts)

- `records_total`: stored raw records, all time; includes items not yet classified.
- `records_with_refinement_total`: distinct raw records with at least one current
  refinement, counted once regardless of output item count or content kind.
- `pending_records_total`: records with no current refinement and no ignored
  disposition, matching the refinement selection definition.
  `records_total = records_with_refinement_total + pending_records_total +
  ignored_records_total`. A non-event/unknown result is still a refinement result;
  it is not backlog merely because it is not an event.
- `ignored_records_total`: records marked with an ignored disposition
  (`model_declined` or `qc_rejected`) so automatic refinement retries skip them.
  Disposition precedence is with-refinement, then ignored, then pending. Only this
  aggregate is exposed; per-record reasons stay operator-side.
- `oldest_pending_captured_at`: earliest original capture time among pending records,
  or null for empty backlog. Show this as the age of the oldest pending capture,
  not measured queue wait time. Keep the same capture-time import caveat.
- Each ingestion-week bucket contains `records`, `with_refinement`, `pending`, and
  `ignored`.
  The latter two partition the records **captured in that week as of the current
  report**. They do not measure how many refinement jobs completed during that week.
  Refining an old record updates that old ingestion cohort's coverage, not this
  week's ingestion count. These are current-state snapshots, not historical backlog.
- Provide the same coverage/backlog totals per source. Include old pending records
  outside the displayed weekly window in all-time backlog totals.

### Refinement output (item counts)

- `refinement_items_total`: number of current refinement rows, across all kinds.
- `refinement_items_by_kind`: event, advertisement, announcement, non_event, unknown;
  explicit zero counts, whose sum equals `refinement_items_total`.
- `event_items_total`: the event subset. UI: “Refined event items”; explain this
  includes past events and is not deduplicated across sources. A single input may
  yield multiple output items; neither output count nor displayed calendar occurrence
  count equals the number of records processed. Do not count a limited events API page.
- `last_refined_at`: most recent timestamp among current refinement results, globally
  and per source; null if none. It is not the last successful batch/job timestamp.
- “Has refinement” does not guarantee quality or a successful LLM call: existing QC
  rejection/unknown outputs can also produce persisted refinement rows. Do not label
  coverage as a success rate, or infer failures/running work from pending records.
- Re-refinement replaces stored rows. Therefore these metrics describe current output,
  not lifetime throughput, attempt/failure counts, first refinement times, or immutable
  weekly completion history. Durable refinement-run telemetry is a separate follow-up,
  not part of source-sync tracking. No inferred throughput chart in this scope.

### Sources, cities, and time boundaries

- `supported_cities_total`: current registry size.
- Per source: ingestion/coverage/backlog totals, refinement output totals/by-kind,
  ingestion-week coverage, latest captured timestamp, and latest refinement timestamp.
  “Latest captured record” and “Latest refinement result” are distinct from last sync.
- Per city: registry metadata, refined event-item total, and number of distinct sources
  with event refinements assigned to that city. Raw records do not have an authoritative
  city before refinement: do not invent per-city ingestion/backlog figures by assigning
  all of a source's records to one city. No inferred source-to-city configuration.
- Unassigned/unsupported city event counts are separate global buckets, so registered
  city totals plus those buckets reconcile with `event_items_total`.
- Week starts are Monday, half-open intervals, `Europe/Vilnius` reporting timezone
  for this first global page. Return that zone and explicit week boundaries; never
  use server/browser timezone implicitly. Default 8 weeks, accepted range 1..52.
  Current week is partial and labelled. Future timestamps must not inflate current
  counts: cap the current bucket at the report's single `as_of` instant.
- Aggregate independent record/refinement counts before combining; joins must not
  multiply records by their refinement/occurrence count. Zero buckets stay visible.
- Phase A sources are observed source names in stored records. A source with no
  stored records appears once sync tracking records an attempt in phase B. This
  is an observed inventory, not a list of currently enabled source configurations.

## Architecture

Small typed read model in `pino-core`, SQL aggregate queries behind the storage
boundary, explicit response models in `pino-web`, and a React Query consumer.
The UI never runs CLI commands. No import from CLI into web. Keep HTTP models
separate from the reusable core report. Use existing dependency-injection style;
add a thin adapter only if it helps the boundary, not a generic repository hierarchy.

Proposed API: `GET /api/stats?weeks=8`. Response contains `as_of`,
`reporting_timezone`, `ingestion_time_basis`, `weeks` (start/end and partial flag),
`totals` (ingestion/coverage and refinement output clearly separated), `sources`, and
`cities`. Sync-related fields are additive in phase B; phase A makes no health claim.
Keep `/api/cities` unchanged for routing. The stats endpoint is a DB-only read: no
source/LLM calls, writes, schema initialization, or shell execution. Existing API
error handling and deadlines apply. Use grouped/conditional SQL aggregates, not
unbounded record materialization or one query per source/city.

Documented response example, abridged to one displayed week and one source:

```json
{
  "as_of": "2026-10-27T18:00:00Z",
  "reporting_timezone": "Europe/Vilnius",
  "ingestion_time_basis": "captured_at",
  "weeks": [
    {
      "week_start": "2026-10-26",
      "week_end": "2026-11-02",
      "starts_at": "2026-10-25T22:00:00Z",
      "ends_at": "2026-10-27T18:00:00Z",
      "is_partial": true,
      "records": 4,
      "with_refinement": 3,
      "pending": 1
    }
  ],
  "totals": {
    "ingestion": {
      "records_total": 120,
      "records_with_refinement_total": 104,
      "pending_records_total": 16,
      "oldest_pending_captured_at": "2026-09-01T07:30:00Z",
      "latest_captured_at": "2026-10-27T16:45:00Z"
    },
    "refinement": {
      "refinement_items_total": 150,
      "refinement_items_by_kind": {
        "event": 96,
        "advertisement": 18,
        "announcement": 14,
        "non_event": 12,
        "unknown": 10
      },
      "event_items_total": 96,
      "last_refined_at": "2026-10-27T17:10:00Z"
    }
  },
  "sources": [
    {
      "source": "vilnius-events",
      "ingestion": {
        "records_total": 120,
        "records_with_refinement_total": 104,
        "pending_records_total": 16,
        "oldest_pending_captured_at": "2026-09-01T07:30:00Z",
        "latest_captured_at": "2026-10-27T16:45:00Z"
      },
      "refinement": {
        "refinement_items_total": 150,
        "refinement_items_by_kind": {
          "event": 96,
          "advertisement": 18,
          "announcement": 14,
          "non_event": 12,
          "unknown": 10
        },
        "event_items_total": 96,
        "last_refined_at": "2026-10-27T17:10:00Z"
      },
      "weeks": [
        {
          "week_start": "2026-10-26",
          "week_end": "2026-11-02",
          "starts_at": "2026-10-25T22:00:00Z",
          "ends_at": "2026-10-27T18:00:00Z",
          "is_partial": true,
          "records": 4,
          "with_refinement": 3,
          "pending": 1
        }
      ]
    }
  ],
  "cities": [
    {
      "city_id": "lt/vilnius",
      "country_code": "lt",
      "slug": "vilnius",
      "name": "Vilnius",
      "timezone": "Europe/Vilnius",
      "event_items_total": 92,
      "sources_with_event_items": 1
    }
  ],
  "supported_cities_total": 1,
  "unassigned_city_event_items_total": 3,
  "unsupported_city_event_items_total": 1
}
```

`/status` is an explicit React route before the wildcard city handler; reserve its
slug from city aliases. Add a small status link to the event header and a return link
to `/vilnius`. Do not refactor event filtering, list virtualization, or global layout.
Use Mantine components/tokens and module CSS when needed. Tables should remain usable
on narrow screens. Render loading, retryable error, empty, and successful states.

## Serial tasks and checkpoints

| Task | Deliverable | Dependency | Commit/review checkpoint |
|---|---|---|---|
| 1 (complete, uncommitted) | Ingestion, refinement/backlog read model and aggregation | Approved metric contract | Review/tests; commit a coherent backend unit |
| 2 | `/api/stats` endpoint and schema | 1 | Review API contract; commit before frontend |
| 3 | `/status` page with ingestion, refinement/backlog, sources, cities | 2 | Manual UI review; commit/release optional useful phase A |
| 4 | Durable source-sync attempt storage and migration | 3 accepted | Review migration; commit before any shared-DB operation |
| 5 | Ingestion records attempts/outcomes | 4 | Review failure/cursor semantics; commit CLI/core unit |
| 6 | Sync status in report, CLI, and page | 5 | Manual review; commit and live acceptance |

One OpenCode run per task, on the approved previous result. Run serially. Each task
brief is in `docs/tasks/source-status/`. The worker may solve routine details but
must stop/report if changing metric meaning, schema scope, ingestion semantics,
public fields, dependencies, or infrastructure seems necessary.

The supervisor reviews the diff and relevant tests; repairs go back to the same
OpenCode session unless trivial. Avoid steering every edit or repeating full checks
without a change. At each handoff report changed files, exact checks, remaining
limits, and whether the worktree has untracked required files. No agent commits,
pushes, deploys, or runs live ingestion unless explicitly asked. User commits give
the next isolated task a reproducible baseline; do not require a commit for every
intermediate edit inside one task.

## Sync semantics (phase B)

Use a small `source_sync_runs` table with one row per attempt: attempt ID, source name, UTC
started/completed timestamps, outcome, fetched/inserted/duplicate counts, and an
optional safe failure-stage code. No raw exceptions or source settings in this table.
An attempt is durable before source fetch. Terminal completion is recorded after
required fetch/store/cursor work; successful zero-result and duplicate-only runs count
as success. Existing non-fatal media download warnings remain non-fatal.

The page shows **last attempt** and **last successful sync** separately. A failed
attempt does not erase the previous success. An unfinished attempt is “unfinished”
(or “completion not recorded”), not claimed to be currently running or healthy.
No attempt means “No sync recorded”, not failure. Do not backfill outcomes from old
records or cursor timestamps. “Last recorded outcome” is more honest than a green
live-health badge: no schedule-based stale/offline inference in this scope.

Select last attempt by maximum `(started_at, id)`; select last successful sync
independently by maximum `(completed_at, id)` among successful terminal rows. An older overlapping completion must not replace the latest
attempt. Individual inserts may already have committed if a later item fails:
record partial counts truthfully and preserve existing pipeline error behavior.
If status persistence fails, surface that failure; never claim telemetry was saved.
Do not try to write a fallback failure row recursively against an unavailable DB.

Adapter-construction/config-load failures currently happen before `CheckPipeline`.
This slice tracks attempts actually started by the pipeline; startup failures remain
CLI errors, not fabricated per-source runs. Disabled/unattempted sources do not
create fake runs. Explicit inventory/config synchronization can be a later task.

No worker retries or fetching triggered from the page. No run-history browser,
retention job, heartbeat, alerting thresholds, or source registry redesign yet.

## Shared-DB rollout

Tasks 1–3 require no migration. For task 4 onward, remember local and production DB
are shared. Review and commit the additive migration first; test on disposable SQLite
and PostgreSQL if available. Coordinate when the new schema is applied with release
schema checks; do not run local CLI commands that auto-migrate the shared DB during
development. Keep old readers compatible and use the current release/deploy workflow.
Treat tasks 4–6 as one release unit: do not apply the task-4 migration immediately
after writing it. The current application checks exact schema revisions, so
coordinate the workstation and production upgrade rather than assuming old readers
can continue after the schema advances.
After compatible rollout, one deliberately authorized real `pino check` is needed to
populate honest sync data. Until then, “No sync recorded” is the correct display.

Acceptance: real `/status` direct load/reload, known totals and week bounds, city
links, public-field safety, error handling, and sync success/failure/zero-new-record
fixtures. Live source fetching is a separate explicit action, never a test dependency.
