# Task 6 — release instructions and live smoke checklist

Task 6 adds recorded source-sync facts to the existing read-only status report,
`GET /api/stats`, the `/status` page, and a new read-only CLI command:

```bash
uv run pino sources health
```

The command uses the same core report interpretation as the API and page. It
requires the existing schema, checks it with `require_current_schema`, and never
auto-migrates. It performs no source fetch, writes, or refinement calls.

No shared migration, deployment, or source fetch was performed while implementing
this task. Those actions require deliberate user authorization and must not be
started by this implementation or by the smoke checklist alone.

## Release unit

Treat tasks 4–6 as one release unit:

1. Review and commit the additive `source_sync_runs` migration (task 4), the
   pipeline attempt recording (task 5), and this reporting/UI work (task 6).
2. Coordinate the workstation and production schema upgrade before deploying
   readers that expect the current revision. The application checks exact schema
   revisions; do not assume old readers can continue after the schema advances.
3. Apply the additive migration only when authorized. Do not run local CLI
   commands that auto-migrate the shared database during development.
4. Deploy the API/SPA and CLI together. Restart the API after the schema is
   current so its startup schema check passes.
5. Only after an authorized release, run one deliberately authorized real
   `uv run pino check` to populate honest sync data. Until then, “No sync
   recorded” is the correct display.

Do not deploy, migrate, or fetch sources without explicit authorization. Do not
run `pino check` as part of an automated test or smoke check.

## What the page and command show

Per observed or attempted source:

- Last recorded attempt selected by `(started_at, id)`.
- Last successful completion selected independently by `(completed_at, id)`.
- `unknown` / “No sync recorded” when no attempt exists.
- `unfinished` when no completion is recorded; it is not claimed to be running
  or failed.
- Terminal `success` or `failure`; a successful zero-insert run is success.
- Safe counts and UTC timestamps. Failure may include only the allowlisted stage
  `fetch`, `store`, or `cursor`. Raw exceptions, URLs, configuration, and source
  settings are never exposed.
- A newer failure or unfinished attempt does not erase the prior success.

Sources observed in stored records are unioned with attempted source names.
Attempted sources with no raw records appear with explicit zero phase-A ingestion,
refinement, and weekly values. Source names are never synthesized from config.
Phase-A totals and city semantics are unchanged.

## Live smoke checklist

Perform only after an authorized release with a current schema.

- [ ] `uv run pino sources health` exits successfully and prints one row per
      observed/attempted source.
- [ ] With no sync runs, every source shows “No sync recorded” and no failure or
      availability claim.
- [ ] After an authorized `uv run pino check`, a successful source shows a
      terminal success, UTC started/completed times, and fetched/stored/duplicate
      counts. A zero-new-record or duplicate-only run still shows success.
- [ ] A source with attempts but no stored records appears with zero raw-record,
      refinement, and weekly values in `/api/stats`.
- [ ] A failed attempt shows failure and an allowlisted stage only; it does not
      erase the last successful completion.
- [ ] An unfinished attempt shows “Unfinished” or “Completion not recorded”, not
      running or failed.
- [ ] `/status` direct load and reload render the sync section with UTC timestamps
      and preserve the existing ingestion, weekly, refinement, and city sections.
- [ ] Public API responses contain no raw exception text, URLs, source settings,
      credentials, payloads, or filesystem paths.
- [ ] The page and CLI agree on the same source states and last-success values.
- [ ] Existing `uv run pino sources stats` publication-grid output is unchanged.
- [ ] Confirm sync is presented separately from refinement backlog/output and
      media-upload freshness; a successful sync may leave refinement backlog.

## Rollback note

The migration is additive, but readers check exact schema revisions. If the
release must be rolled back, coordinate the application version and schema state
together. Do not run ad-hoc destructive SQL against the shared database.
