# Web routing: sanity review and staged design

Status: proposed roadmap; slice 1 was implemented and compared on 2026-10-18,
and accepted by the user. City support is the next delivery priority as of 2026-10-20;
the [city proposal](web-routing-cities.md) records the updated decisions and scope.
The [city backend foundation](web-routing-cities-backend-brief.md) is now implemented
in the main working tree with 309 Python tests passing. Historical city population
was completed on 2026-10-24. SPA city routing and explicit city-timezone browsing are
implemented in the main checkout: 110 frontend tests and build pass, including 41
city/timezone tests rerun under UTC and New York. HTTP integration remains pending.
The one-off historical Vilnius stamp script is implemented and verified with 9 focused
tests. It stamped 753 existing null-city event refinements in the shared database;
the follow-up preview returned zero. See the city proposal for the operation record.
DeepSeek V4.1 Flash's implementation, with separately recorded supervisor repairs,
is kept in `web/src/`. Baseline: `bd7bc82`. The earlier
[architecture review](web-routing-architecture-review.md) remains background, not a
blanket authorization to change infrastructure.

## Sanity review

The list-first direction holds up. Use real event links, small optional previews,
and standalone details. Defer panels, contextual routing, and swipe navigation.

The current code still has the prerequisites identified in September:

- `Refinement.id` is generated and `DatabaseStore.replace_refinements` deletes the
  previous rows. Neither that ID nor `(record_id, item_index)` is a durable public
  event identity: extraction can reorder, split, or merge items.
- Source records have idempotency fingerprints, but a source post can contain several
  events. A record ID alone cannot identify each event in a digest.
- `location` is display text; source `location_scopes` are hints, not an indexed city
  assignment. A city route without backend filtering would misrepresent the feed.
- The list service expands schedules within a bounded query window. Details must
  resolve independently of that window and limit, and must not expand an unlimited
  recurrence to construct a page.
- The frontend uses component routes, form-local filters, browser-local dates, and
  a virtualized list. Filter URLs can be delivered before identity and city work.
- Production explicitly ships static assets plus Python. A React SSR server would
  change the infrastructure contract, release artifact, probes, and rollback.

Two refinements to the old proposal: do not make full cross-source deduplication a
prerequisite for the first public links; do not bundle URL state, identity, city
classification, SSR migration, and scroll restoration into one implementation.

## Proposal A: public identity and city data

Introduce a durable public event entity, with a generated opaque ID and a separate
association to source records/current refinements. Refinement IDs remain internal.
Occurrences belong to an event; they are not separate identities for every list row.

Start with source-local identity. Preserve associations on unambiguous reprocessing;
do not derive public IDs from mutable titles, dates, location, or item positions.
Cross-source duplicates may initially have separate public IDs. Later consolidation
must preserve old URLs through aliases, not replace IDs silently.

Before schema implementation, define fixtures and reconciliation rules for one-to-one
updates, reordered multi-event posts, splits, merges, removals, and source edits.
An ambiguous match must not silently attach an old URL to a different event. Record
an unresolved association for review; retain the previous published representation
until explicitly superseded or withdrawn. This publication-state policy needs a
concrete storage/API design before public URLs ship.

Add a manually maintained city registry (`country_code`, `city_slug`, IANA `timezone`).
Initially use `lt/vilnius`; country is not UI language. Geographic scope is coarse and
provider-owned. The existing LLM refinement process selects at most one registry city
per extracted event using source context; it can override a source default. Validate
the result deterministically, storing unknown/invalid cities as null while retaining
the event. The city proposal specifies an indexed refinement field, historical
population, and city changes or clearing during ordinary re-refinement. Multiple city
memberships for one event are out of scope. Filter before scan and result limits.
Keep venue text separate from city membership.

Migration acceptance: fresh and existing SQLite/PostgreSQL databases, deterministic
city validation, transactional refinement replacement, explicit historical population,
and unchanged unscoped list semantics. For the separate public-identity work, also
require stable IDs after reordering, no silent retargeting, and repeatable backfill.
Use disposable databases only; live migration/publication is separate work.

## Proposal B: route and rendering contract

| Route | Contract |
| --- | --- |
| `/` | Entry redirect to a supported IP-inferred city when available, otherwise Vilnius |
| `/lt` | Entry redirect to a supported inferred Lithuanian city, otherwise Vilnius |
| `/vilnius` | Supported short route rendering the same city feed as `/lt/vilnius` |
| `/lt/vilnius` | Explicit city feed; normalized lowercase country/city identifiers |
| `/{country}/{city}/event/{public_id}` | Stable standalone event page; resolve by globally unique ID and redirect old city paths |
| `/event/` | Existing list during migration; compatibility redirect to Vilnius preserving filters |

These route choices include the user's 2026-10-24 clarification: both short and
country-qualified city URLs remain valid, with explicit short aliases for supported
cities. Historical null-city events can be stamped Vilnius with a one-off preview/apply
script against the shared local/production DB; no LLM reprocessing is needed for that
data decision. IP matching needs a
concrete data source; use the documented fallback in its absence. The city proposal
distinguishes SPA navigation from real HTTP redirect/not-found integration.

`GET /api/events/{public_id}` resolves without list filters, a current-date window, or
list result limits. Return the normalized schedule and event bounds; bound any
optional occurrence preview. Distinguish unknown IDs (404), explicitly withdrawn
content (documented tombstone policy), and dependency failures (503).

Keep one public data projection for HTML and JSON: title, description, venue, schedule,
source attribution, images, and current publication status. Never expose debug data.
Escape source text, validate outbound links, and generate canonical URLs from trusted
configuration. Cancellation/expiry must propagate to both visible HTML and metadata.

Rendering constraint confirmed by the user on 2026-10-18: preserve Python + SPA and
explore simpler SEO/public-HTML options first. Do not introduce a Node/JS SSR runtime.
The rendering implementation remains separate from the first slices:

- Preferred first experiment: Python renders a standalone public event page from the
  same service projection as the API. The SPA continues to own interactive browsing.
  Ordinary links between them are acceptable initially; do not require React hydration
  of Python HTML. Use an autoescaping template, real HTTP status codes, canonical and
  sharing metadata, and bounded database work. Extend existing packaging for template
  assets and arrange explicit Caddy forwarding for public routes in infrastructure.
- Then evaluate a small Python-rendered city landing/listing with genuine event links
  and a clear link into the interactive SPA carrying city/filters. If the SPA later
  enhances that same page, define the handoff without duplicate content, focus loss,
  or scroll jumps. Avoid maintaining two complete interactive UIs.
- Prerendering is viable only with content-driven regeneration and cancellation/expiry
  invalidation. Software-release-only builds are insufficient for changing events.

Compare the Python page experiment against prerendering on freshness, publication
complexity, and duplicated presentation before committing to the full city experience.
A React SSR service is deferred, not a dependency or authorized migration. Reopening
it would require a new deployment decision and changes to the infrastructure contract,
release packaging, process supervision, probes, and rollback.

React Router documents SSR as requiring supporting deployment and prerendering as a
build-time operation: [rendering strategies](https://reactrouter.com/start/framework/rendering).
Choose against the locked package version when implementing; do not upgrade the
frontend framework incidentally.

Public rendering acceptance: useful no-JS HTML, correct HTTP status/canonical URL,
share metadata, escaped content, fresh cancellation handling, bounded queries, and
matching initial/client content. Recheck search-engine structured-data guidance then;
special event search eligibility is not a promised benefit of this work.

## Proposal C: browsing and history

Public filters belong in the query string. Hidden-event preferences remain local.
The first slice preserves the existing `/event/` route, filter controls, and date
semantics; its detailed contract is in [the implementation brief](web-routing-slice-1.md).

After city support, use the city's timezone for default days, picker interpretation,
grouping, and labels, including DST. URLs preserve explicit instants. This needs tests
from browsers in different timezones; the current test command's timezone pin is not
a product fix.

After event pages, preserve a list location key, occurrence/day anchor, offset, and
focused element in session/history state. Restore after data and virtualized geometry
are ready. Fall back to the nearest available day when an event disappears. Keep
restoration separate from shared URL filters. A direct event visit needs no list fetch.

Inline expansion uses a button and bounded content; title links navigate normally.
Test keyboard focus, Back/Forward, loaded images, changed row heights, and removed
events on narrow and wide screens before considering a desktop panel.

## Delivery sequence

| Slice | Deliverable | Depends on | Acceptance gate |
| --- | --- | --- | --- |
| 1 | URL-backed filters on existing list | Nothing new | Direct URL, reload, edits, Back/Forward, invalid values, tests/build |
| 3a (complete) | Registry, validated LLM assignment, API filter and one-off historical stamp | City proposal and source context | Backend/script tests pass; 753 shared-DB rows stamped and preview verifies zero remaining |
| 3b (complete, undeployed) | City routes and timezone-correct browsing | 3a + 1 | Both route forms preserved; client redirects, DST and foreign-timezone tests pass |
| 3c | HTTP routing integration; optional IP matching | 3b + infrastructure routing contract | HTTP redirects/404s, query preservation, inference fallback |
| 2a | Identity reconciliation specification + fixtures | Identity policy decisions | Reordering/split/merge/removal behavior reviewed |
| 2b | Durable event identity and migration | 2a | Migration and reprocessing invariants |
| 4 | Standalone detail API + client page | 2b | Direct/past/unlisted event access, true not-found state |
| 5a | Python public event HTML experiment + metadata | 2b + detail service from 4 | No-JS event HTML, status codes, fresh content, template packaging |
| 5b | Bounded public city HTML and SPA handoff | 3b + 5a experiment review | No duplicate content, crawlable links, deployment acceptance |
| 6 | Bounded expansion and browsing restoration | 4 | Realistic mobile/keyboard/history verification |

Each row is independently reviewable; split migrations and user-facing work further
when useful. Existing slice numbers are retained for reference; city slices now come
first. Refinement city assignments do not depend on public event IDs. Slices 2 and 3 can
be designed independently. Slice 1 is deliberately a
small useful precursor, not a substitute for the identity prerequisite to event URLs.

## Model comparison

DeepSeek and MiMo receive the same slice-1 brief and baseline in isolated worktrees.
Use the exact OpenCode free model IDs and its default model settings; record the
actual run IDs, duration, verification results, and any intervention. Neither worker
may inspect the other's output. No package upgrades, backend changes, or deployment.

Astra reviews anonymized candidate diffs against the brief, with correctness taking
priority over speed or diff size. Evaluate URL/form/request consistency, navigation
races, tests of user behavior, scope, and maintainability. Independently rerun checks.
Preserve both candidates before repairs, retain the better implementation in the
main working tree, and label any supervisor repairs separately. A failed provider run
is an availability observation, not evidence of coding quality. One task only gives
a provisional default model; revisit on backend work.
