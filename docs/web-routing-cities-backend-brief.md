# City backend foundation: DeepSeek implementation brief

Implement only this bounded first part of city slice 3a. Read `AGENTS.md` and the
recent entries at the top of `docs/progress.md`. `docs/web-routing-cities.md` is
background; this brief controls implementation scope. Baseline: `ff356f6`.

## Deliverable

The existing LLM refinement pipeline selects a supported city or null. The city is
stored on the refinement, can change/clear on re-refinement, and can filter the event
API before database scan/result limits. Existing unscoped browsing remains compatible.

## Implementation contract

1. Add a small manually maintained registry in `pino_core` (a Python module is enough;
   no config framework or database registry management). Each entry exposes `id`,
   `country_code`, `slug`, `name`, `timezone`. Initially publish only `lt/vilnius`,
   `lt`, `vilnius`, `Vilnius`, `Europe/Vilnius`. Stable IDs include country and city.
   Test alternative cities/timezones with fixtures, not extra production entries.
2. Normalize candidate IDs by stripping surrounding whitespace and lowercasing strings;
   accept only an exact registry key after that. Null, missing, empty, unknown,
   non-string, or malformed values resolve to null. No aliases, fuzzy lookup, source
   name inference, or automatic registry expansion in this slice. Keep one shared
   registry/normalizer for refinement validation, API validation, and metadata.
3. Add nullable `city_id` to `Refinement`, storage serialization/deserialization, and
   portable SQLAlchemy metadata with an index. Add Alembic revision after `0002`;
   old refinements keep null and all their existing data. Fresh and existing databases
   must work. Normal refinement replacement persists the new city atomically with
   the rest of its rows. No record-level city association or manual override system.
4. Extend the existing refinement prompt/response with `city_id`, supported keys,
   and the meaning of source `location_scopes` as context that the LLM can override.
   Keep the current single-item response protocol; do not restore a historical
   multi-item extractor. Reject unknown city values without rejecting the event.
   Preserve raw values in existing `debug.raw` metadata. Explicit null/unknown results
   must never fall back to the source default after validation. Keep venue `location`
   unchanged. No additional LLM calls or model/provider changes.
5. Add optional `city` query parameter to `GET /api/events`. Omitted preserves existing
   behavior; present but empty/invalid/unknown returns 400 rather than an unscoped feed.
   Use canonical normalized IDs in repository/storage queries. Filter in SQL before
   the candidate scan limit and before occurrence projection/result limits. Do not
   change callers of unscoped storage queries unnecessarily. Return nullable `city_id`
   on event items as additive metadata.
6. For a selected city, resolve missing/naive date bounds and schedule projection using
   the city's timezone; explicit offset instants retain their meaning. Schedule-local
   timezones continue to determine occurrence instants. Return the selected city's
   timezone in `EventListResponse`. Unscoped defaults stay compatible; injected local
   timezone should be accurately reflected in metadata. Avoid shared mutable service
   state that leaks a request's city/timezone into another request.
7. Add `GET /api/cities` returning `{ "cities": [ ...registry entries... ] }` with
   deterministic ordering and public metadata only. Keep normal API error behavior.

## Hard scope boundaries

Allowed: `packages/pino-core/src/`, relevant `packages/pino-core/tests/`,
`apps/pino-web/src/`, and relevant `apps/pino-web/tests/`.

Do not edit frontend, CLI, source adapters, dependencies/lockfiles, existing golden
fixtures, existing migration revisions, unrelated docs, progress log, infrastructure,
or deployment. No public identity work, redirects, SSR, geolocation, multi-city event
memberships, review queues, or generalized registry framework. Historical population
and its CLI/preview are a follow-up; this migration must not perform LLM calls or
autoassign existing rows. Do not read or operate actual `.pino` databases, production
services, or another model's worktree. Use disposable test databases. No commit/push.

## Required verification

Add focused behavioral tests for:

- Accepted/normalized, unknown, null, malformed (including JSON arrays/objects) city
  values; prompt includes registry and retains source context; raw candidate retained.
- LLM override of source context using a synthetic second supported city; invalid
  candidate does not silently become the source city. Preserve current response shape.
- Stored city round-trip and change/clear on transactional refinement replacement.
- Pre-scan filtering: other-city candidates would exhaust a small scan limit before
  the selected city's record; the selected city's event must still be returned.
- Unscoped API compatibility, selected-city filtering excluding unassigned records,
  unknown/empty-city 400, city metadata endpoint, additive event city metadata.
- Selected-city timezone resolution/projection/response with a synthetic foreign-zone
  city and unchanged explicit instants; no leakage into a subsequent unscoped request.
- Migration of an existing SQLite DB with refinements at revision `0002`, preserving
  all data with null city; fresh schema/index. PostgreSQL migration SQL compilation
  and query compilation using existing test patterns. Never claim a live PostgreSQL
  integration pass when only compilation was exercised.

Run focused core/web tests, then the repository Python suite and Ruff, and
`git diff --check`. Use an isolated environment for this worktree so imports cannot
silently resolve to the main checkout. Keep locked dependencies unchanged. If an
unrelated baseline check fails, report evidence rather than broadening scope.

Finish with changed-file summary, checks with results, and limitations. Leave all
changes uncommitted for supervisor review. If a requirement cannot be met within
scope, report it rather than expanding the task.
