# City routing proposal

Status: design proposal updated from user decisions through 2026-10-24. URL filter
implementation accepted. The backend foundation is implemented in the main working
tree; the historical Vilnius stamp was applied on 2026-10-24. SPA city routing is
implemented in the main checkout; HTTP routing integration remains pending. This proposal
supersedes the city-assignment and route choices in the earlier architecture review.

## Implemented backend foundation

The [backend brief](web-routing-cities-backend-brief.md) was implemented by OpenCode
`opencode/deepseek-v4.1-flash-free`, with GPT Luna coordinating automation and Astra
reviewing the code. Baseline: `ff356f6`; original implementation retained in
`.pino/worktrees/cities-deepseek` on `experiment/cities-deepseek`. Session metadata and
integration hashes are in `.pino/cities-implementation/` (local, ignored by Git).

Delivered: manual Python city registry (Vilnius only), normalized LLM `city_id` with
raw-output retention, nullable indexed refinement storage and migration `0003`,
`GET /api/cities`, `GET /api/events?city=lt/vilnius`, additive event city metadata,
pre-scan SQL filtering, and request-local city timezone handling. Existing unscoped
API behavior is retained. The initial backend delivery did not assign historical data
or migrate a live database; the later historical stamp is recorded below.

DeepSeek added two timezone tests after review; no supervisor production-code repairs
were needed. Independent verification in the main checkout: 309 Python tests pass,
Ruff passes, and `git diff --check` passes. Tests exercise SQLite migrations and
PostgreSQL SQL compilation; a real PostgreSQL migration was not exercised. The
existing Starlette/httpx test-client deprecation warning remains.

The one-off historical Vilnius script has been applied to the shared database.
SPA city browsing is delivered below; HTTP redirect integration remains a separate delivery.
The frontend was unchanged by this backend foundation.

## Implemented SPA city browsing

Delivered on 2026-10-24 from baseline `9379050`, using OpenCode DeepSeek V4.1 Flash
in `.pino/worktrees/cities-spa-deepseek`. Both `/vilnius` and `/lt/vilnius` render the
same city feed while preserving the requested form. `/`, `/lt`, `/event`, and
`/event/` replace-navigate to `/lt/vilnius`, retaining query parameters and hashes.
Only registered cities load events; metadata loading/error/retry and unsupported
routes have distinct states. Event requests and cache keys use the canonical city
ID, with no previous-city placeholder results during a city change.

Defaults, picker edits, calendar arithmetic, grouping and labels use the city IANA
timezone. Explicit URL instants remain intact. Newly ambiguous picker times choose
the earlier instant; unchanged later-overlap selections are preserved. Nonexistent
picker times show an error without navigating. A composed Mantine calendar/time
picker avoids browser-local DST conversion; selected years below 100 use a native
date input to avoid Mantine/dayjs interpreting them as 1900–1999.

Astra reviewed the implementation. DeepSeek repaired overlap resolution and the
browser-local picker conversion after supervisor review. Supervisor repairs in the
main checkout clear errors on a no-op Reset, normalize invalid URL filters on
unchanged date actions, and guard early-year date editing, with regression tests.
The worker's original candidate is preserved. Local logs and original integration
hashes are in `.pino/cities-spa-implementation/`. OpenCode resumed the same session
after an inactivity interruption; the parent took over automation when Luna reached
its usage limit.

Main-checkout verification: 110 frontend tests pass; the 41 city/timezone tests also
pass separately under `TZ=UTC` and `TZ=America/New_York`; TypeScript and production
build pass. The existing bundle-size warning remains. Router/picker checks use
jsdom, not a deployed browser. No dependencies, backend, or infrastructure changed
in this SPA slice. Changes are uncommitted and undeployed. Real HTTP redirects/404s,
IP inference, public event pages, and SEO HTML remain later slices.

## One-off historical stamp

Applied on 2026-10-24 to the configured shared PostgreSQL database, with refinement
cutoff `2026-10-23T23:45:45+00:00` and expected count 753. The current schema check
passed, so no migration was run. Updated 753 null-city event refinements: afisha-vilnius
314, kaveikti-vilnius 109, reforumspace-vilnius 91, vilnius-belarus 53, vilnius-events 186.
The follow-up preview at the same cutoff returned zero. Original IDs and city values
were saved locally in `.pino/cities-implementation/stamp-20261024-before.json`.

Use [stamp_vilnius_city.py](../scripts/stamp_vilnius_city.py) against the shared
database once. It requires the current schema, previews by default, and stamps only
null-city event refinements at or before a fixed refinement timestamp. Event dates
do not affect eligibility. Existing assigned cities and all other fields are preserved.

Capture a cutoff and preview using the configuration for the shared database:

```sh
stamp_before="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
uv run python scripts/stamp_vilnius_city.py --config config.yaml --before "$stamp_before"
```

The output reports the cutoff, total eligible refinements, and counts by source.
To apply, reuse that exact cutoff (or paste the reported ISO value), replacing `N`
with the preview's total eligible count:

```sh
uv run python scripts/stamp_vilnius_city.py --config config.yaml --before "$stamp_before" --apply --expected-count N
```

An unexpected affected-row count aborts and rolls back the transaction. After a
successful run, the same preview should report zero eligible rows. No live database
was accessed while developing the script; the subsequent shared-DB application is
recorded above. DeepSeek wrote the script and its tests;
supervisor review and independent main-checkout verification passed all 9 focused
tests and scoped Ruff. These tests use disposable SQLite databases; the actual
PostgreSQL update subsequently completed with the expected row count.

## Confirmed direction

- Keep Python + React SPA. Deliver city support before durable public event identity.
- The supported city list is manually maintained. City scope is deliberately coarse
  and provider-owned; source metadata supplies context/defaults to the existing LLM
  refinement process. The refiner selects one city for each event and can override
  the source default. Deterministic validation accepts only registry cities.
- Providers also decide online scope. Online, country-wide, worldwide, and unknown
  geography must not silently become Vilnius. Their eventual type/category UX is deferred.
- Each refined event has at most one city. Multiple city memberships for one event
  are out of scope; no special multi-city workflow is required. Items extracted from
  the same source record need not have the same city.
- Canonical city route: `/<country>/<city>`, initially `/lt/vilnius`.
  Country is geography, not interface language. Both `/vilnius` and `/lt/vilnius`
  remain usable city routes, rendering the same feed while preserving the requested
  URL. The country-qualified path remains the canonical metadata target when public
  HTML is added. This replaces the earlier short-path redirect proposal.
- `/` and `/lt` are entry redirects. Use a supported city from IP location when
  available; otherwise use Vilnius. `/lt` only accepts a supported Lithuanian match.
- Future canonical event route: `/<country>/<city>/event/<public_id>`.
- Defaults, date pickers, grouping, and labels use the selected city's timezone.

## Conservative assignment lifecycle

Use a small manually maintained city registry with stable key, country code, slug,
display name, and IANA timezone. Initially seed `lt/vilnius`, timezone `Europe/Vilnius`.
Use the same registry for refinement validation, API validation, and navigation.

Keep the existing source-record-to-LLM-refinement architecture. Proposed storage is
an indexed nullable `city_id` on each refinement, separate from free-text venue
`location`. No durable record-level assignment table or new event entity is needed
for this slice. The city's lifetime follows the rest of the refined event data.

Provide the supported keys and source context (including configured `location_scopes`)
to the existing refinement call. Request one registry key or null per extracted item.
The LLM may select a different supported city when the event warrants it. Source
scope is guidance, not an immutable assignment or a post-validation fallback.

Validate the returned key deterministically. Accept exact registry keys after
documented normalization and any explicitly maintained aliases. Unknown, missing,
ambiguous, or malformed values become null; never create a city automatically,
guess a nearest match, or replace a rejected city with the source default. An explicit
non-city result also remains null. Reject the city assignment, not the event itself.
Retain the raw result in existing refinement debug metadata so invalid candidates
can be reported for manual review without adding a review queue or UI in this slice.

Re-refinement may change or clear the city together with the other refined fields.
Validate and persist the new rows atomically using the existing replacement lifecycle;
do not preserve stale city assignments separately. Duplicate ingestion alone does not
change an existing refinement. Registry/default edits do not silently rewrite stored
results: changes take effect on explicit reprocessing. Keep registry keys stable and
defer destructive registry deletion/renaming until stored references are handled.

Schema migrations add the nullable field and index, leaving historical rows unassigned.
On 2026-10-24 the user confirmed that local and production share a database and that
existing events may be treated as Vilnius. Use a one-off script to stamp existing
event refinements whose city is null as `lt/vilnius`. This is an explicit historical
data decision, independent of source-name inference or the ongoing refinement rules.
Preserve any existing non-null city and every other field; no LLM reprocessing is
needed for this operation. Use a fixed refinement timestamp cutoff to exclude later
processing. Preview first, then explicitly apply the expected number of rows in one
transaction, rechecking the predicate during update and rolling back on count mismatch.
Run once against the shared database, not once per environment. Require an already
current schema; this script does not apply migrations.

Future ingestion/refinement already supplies a validated city through the LLM pipeline.
Do not schedule the historical stamp or make it an ongoing default for unknown cities.
Test the script against disposable databases; record an actual shared-DB application
separately from script implementation.

Online/worldwide/country-wide records can be explicitly kept outside city feeds in
this first slice. They remain stored and available through the existing unscoped API.
This is a proposed initial inclusion rule; richer discovery and category presentation
remain separate design work, not a prerequisite for Vilnius routing.

## API and browsing contract

- Add an optional validated city key to `/api/events`; no key preserves existing API
  behavior. A supplied unknown key returns an explicit error, never an unscoped feed.
- Apply city filtering in the database before the candidate scan limit, event limit,
  and occurrence projection. Missing/non-city assignments do not match a city feed.
- Expose supported city metadata through a small endpoint. Include the city in query
  cache keys and return its actual timezone in the event response; the current fixed
  `Europe/Vilnius` response value cannot remain hardcoded for all cities.
- Preserve the accepted query filter contract. Explicit URL instants retain their
  meaning; missing bounds use the selected city's local defaults. Picker changes and
  calendar-day operations use that zone, including DST, regardless of browser zone.
  Existing schedule timezones still determine occurrence instants; city timezone
  determines browsing and display.
- City switching is ordinary navigation: preserve explicit filter instants, categories,
  score, and search; recalculate missing defaults for the destination. Back restores
  the previous city and filters. No special cross-city scroll restoration is needed.

## Route and redirect contract

| Request | Proposed behavior |
| --- | --- |
| `/` | Temporary redirect to a supported inferred city, otherwise `/lt/vilnius` |
| `/lt` | Temporary redirect to a supported inferred Lithuanian city, otherwise `/lt/vilnius` |
| `/vilnius` | Supported short route rendering the same city feed as `/lt/vilnius` |
| `/event/` | Compatibility redirect to `/lt/vilnius`, retaining accepted filter semantics |
| `/lt/vilnius` | Explicit Vilnius feed; never overridden by IP location |
| Known country with no published cities, unknown country/city | Not-found state; do not silently substitute Vilnius |
| `/<country>/<city>/event/<public_id>` | Reserved for later standalone event implementation |

Normalize known routes to lowercase and one trailing-slash convention. Preserve
query parameters through redirects and fragments during client navigation; fragments
are unavailable to the server and require browser-level verification. Use an explicit
alias map, not a global search for matching city slugs: names can be ambiguous across
countries. Both route forms resolve to the same registry ID and query-cache identity.
For example, a future `/batumi` could map to `ge/batumi` alongside `/ge/batumi`; this
does not add Batumi to the current registry. Short paths are registered explicitly
for supported cities. Reserve entry routes and system paths against alias collisions.
Navigation replacement avoids adding redirect-only history entries for entry and
legacy redirects; short city paths themselves do not redirect.

IP selection is best effort and only applies at entry routes. The current repository
has no configured IP geolocation service. First delivery can use the documented
Vilnius fallback; enabling IP matching needs a concrete provider or trusted proxy
metadata contract. Do not add a third-party lookup on every request by default.
Only accept supported registry cities, keep inference bounded, and fall back on
failure. Inferred redirects must not be permanently or publicly cached across visitors.

Caddy currently serves the SPA while Python owns the API. Client replacements alone
do not provide HTTP redirects or HTTP 404 responses. Deliver client routing first if
needed, but track real 308 normalization redirects, 302 entry redirects, and 404
handling as explicit server/edge integration acceptance. This requires a reviewed
infrastructure routing change, not merely a React router edit. Public HTML and metadata
are a later rendering slice within Python + SPA.

## Stable nested event URLs

The user-selected nested route replaces the earlier global `/events/{public_id}`
proposal. Keep the public ID globally unique and independent of country/city. Resolve
the event by ID; location is its canonical browsing context, not its storage identity.
When a published event's city changes, preserve its old route as a permanent redirect
to the current canonical route. Unknown IDs remain not found. Routes for non-city
events remain a later decision.
No event URL should ship using today's replaceable refinement IDs.

## Gradual delivery and verification

1. **City data and API:** manual registry, source context, LLM city selection and
   deterministic validation, indexed refinement city, migration, historical population,
   pre-limit filtering, city metadata endpoint. Verify supported overrides, unknown and
   malformed values, no fallback after rejection, independent cities across extracted
   items, city changes/clearing on re-refinement, atomic replacement, and SQLite/PostgreSQL
   migrations. Use mocked LLM responses for lifecycle tests. Include a fixture
   where another city fills the candidate limit before the requested city's records.
2. **SPA city browsing:** canonical city path, explicit aliases, entry fallbacks,
   not-found UI, query/cache isolation, timezone-aware controls and display. Verify
   direct loads, reloads, Back/Forward, redirect filter preservation, and DST in both
   Vilnius and a foreign browser timezone. Include a synthetic second city/timezone
   in tests even while only Vilnius is published.
3. **HTTP routing integration:** agree the Caddy/Python ownership of redirects and
   unknown paths; verify direct HTTP responses, asset/API exclusions, fallback on
   absent geolocation, and query/fragment behavior. Enable IP matching only once its
   data source and trusted-proxy contract are concrete.

Durable public identity, event pages, and public HTML remain separate subsequent
slices. City routing does not require Node SSR or a new interactive presentation.
