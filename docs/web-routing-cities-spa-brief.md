# City SPA routing and timezone brief

Implement this bounded slice only. Baseline `9379050` includes the city backend and
accepted URL filters. Read root `AGENTS.md` and the recent top of `docs/progress.md`.
The historical Vilnius stamp has been applied separately; do not access any database.

## Routes and metadata

- Fetch supported city metadata from existing `GET /api/cities` using TanStack Query.
  Server registry owns city IDs, names, countries, slugs, and IANA timezones. Only
  `lt/vilnius` is published today; do not add Batumi or other production entries.
- Both `/vilnius` and `/lt/vilnius` render the same city feed while retaining the
  requested route form. Use an explicit short-alias map, initially only
  `vilnius -> lt/vilnius`; do not guess ambiguous city slugs. Country-qualified
  routes resolve any supported registry entry (synthetic second city in tests).
- `/`, `/lt`, `/event`, `/event/` replace-navigate to `/lt/vilnius`, preserving the
  query and hash. This is the agreed fallback; no geolocation service in this slice.
- Normalize known city paths to lowercase and no trailing slash with replace
  navigation while preserving their short/qualified form and query/hash. Unknown
  paths/countries/cities show a useful not-found view, never a default/unscoped feed.
  Reserved system/entry paths take precedence over city aliases. `/batumi` remains
  unknown unless deliberately registered in a later change.
- Do not fetch any event feed until metadata and the requested city resolve. Distinguish
  metadata loading, metadata/API failure (with retry), unknown city, and empty events.
  An API error is not a not-found result. Extract testable route composition from main
  if useful; preserve the existing Mantine/React Query providers and analytics setup.
- Pass the resolved city to event browsing. Request `/api/events` with `city=<id>` and
  include canonical city ID in the event query key. Both route forms share that key.
  Changing cities must not display the previous city's placeholder events; retaining
  previous results during filter edits within the same city is fine. Make the city
  name visible in the existing header. No new city selector or overall visual redesign.

## Dates and accepted URL state

Preserve all accepted filter semantics: five owned query keys, explicit offset/UTC
instants, validation and supported UTC years 2..9998, 370-day absolute interval cap,
category/score/text normalization, unrelated query/hash preservation, Back/Forward,
replace on text edits, push on effective discrete edits, no-op handling, Reset, and
single navigation for a From change that also changes To.

All actual city UI paths must explicitly use the selected IANA timezone for:

- Missing/invalid bounds and Reset: today's city-local midnight; default end remains
  30 calendar days later at the same local clock time. Next month still adds 30 days.
- Picker displayed values and interpretation of changed values. Inspect the installed
  Mantine 9 types/source: DateTimePicker supports wall-clock strings; DatesProvider
  has no timezone setting. Convert actual instants to city wall-clock values at the
  picker boundary and back on edits. Never parse picker wall-clock strings with a
  browser-local `new Date(string)` or store shifted fake instants in URL/filter state.
- Calendar-day arithmetic across DST, event grouping, day/date labels, time ranges,
  all-day/From/Until presentation, and multi-day progress labels/ranges.

UTC/offset bounds from URLs keep their original instants, including either occurrence
of an ambiguous DST hour. Calendar edits use a deterministic wall-time policy: reject
nonexistent spring-forward picker times with a visible field/message error and no URL
change; for a newly entered ambiguous fall-back wall time, choose the earlier instant.
If the picker re-emits its unchanged displayed wall time, preserve the current exact
instant, including a URL-selected later overlap occurrence; that is a no-op, not a
new ambiguous entry.
Calendar-day arithmetic must re-evaluate the timezone offset after the date change;
if its target clock time is nonexistent, advance by the DST gap. Add meaningful tests
and keep the policy documented in the helper. Preserve valid extreme-year behavior.

Use existing dayjs plugins and/or Intl; no new date library or dependency. Keep timezone
helpers small and shared, avoid global mutable timezone defaults. Retaining optional
browser-local defaults on legacy utility helpers is okay for compatibility, but city
browsing must always pass the explicit timezone through the entire display/filter path.

## Scope

Allowed changes: `web/src/` only. Use Mantine tokens and module CSS if needed. Do not
change dependency manifests/lockfiles, backend, migrations, source providers, data,
deployment, SSR, event identities/details, virtualization mechanics, or analytics.
This slice implements SPA routes; actual HTTP redirects/statuses, canonical HTML, and
server/edge changes are subsequent work. No live API/database/service calls, no commit
or push, no reads of other worker worktrees. Mock the API in tests.

## Verification

Preserve the existing 69 frontend tests, adapting harnesses for resolved city props
where needed rather than deleting accepted behavior. Add route-integrated tests for
both city forms, default/legacy redirects and query/hash preservation, normalization,
Back/Forward, unsupported city and metadata failure/retry, no unscoped initial fetch,
correct `city` parameter/cache separation, and no old-city data during city changes.

Add explicit-zone tests that pass in foreign browser timezones: fixed clock around
midnight, picker display and actual edits producing correct UTC URL/request, default
end/Next month crossing spring/fall DST, city day grouping/time/progress presentation,
gap rejection, deterministic overlap, and explicit overlap instants preserved. Include
a synthetic second supported city/timezone; do not add it to production registry.
Check timezone round-trips for existing supported-year edge cases as appropriate.

Run `bun run test`, `bun run build`, and `git diff --check`. Also run the dedicated new
city/timezone tests directly with `TZ=UTC` and `TZ=America/New_York` using installed
Vitest; the package test script pins Vilnius, so it cannot prove foreign-zone behavior.
Use the actual router and actual Mantine picker for key interaction tests; mocking
network and virtualized layout is fine. Do not mock away timezone conversion or URL
synchronization. Stop once required gates pass and report exact results/limitations.

Leave the implementation uncommitted for supervisor review. Keep worker artifacts
in the dedicated worktree; do not copy changes into main yourself.
