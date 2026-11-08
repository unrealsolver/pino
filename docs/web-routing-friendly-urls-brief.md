# Friendly city URLs and date-only filter brief

## Handoff and review gate

This is a scoped implementation brief for **OpenCode model `opencode/deepseek-v4.1-flash-free`**. The user approved the brief and clarified the workflow: two separate tasks in series, with a manual review stop before starting task 2. Both tasks are authorized; the user approved proceeding to task 2 after reviewing task 1. No git commits.

Implement only the web SPA behavior below. Keep work uncommitted for review. Do not change dependencies, backend, database, infrastructure, SEO/canonical metadata, or `docs/progress.md`.

Prepared against `95cd4ed` (`feat: cities web support`). Luna coordinates an isolated worktree and OpenCode run. Task 1 implements only short default routes/links, verifies them, and brings the reviewed changes into the main checkout uncommitted. Then stop for the user's manual review. Only after the user's go-ahead may task 2 implement date-only parsing/serialization. Do not commit, deploy, or apply database changes.

Task 1 completed on 2026-10-26 using the requested DeepSeek model, with Luna
coordinating and the parent reviewing the two-file diff. Changes are in the main
checkout, uncommitted: entry replacements and the Browse Vilnius link now use
`/vilnius`; explicit route forms survive filter edits. Verification: 112 frontend
tests, TypeScript/production build, and diff checks passed; existing bundle-size
warning remains. Candidate and run logs are retained in
`.pino/worktrees/friendly-routes-deepseek` and `.pino/friendly-routes-implementation/`.
Task 1 is now committed by the user as `fc7b2e6`.

Task 2 completed on 2026-10-26 from that baseline using OpenCode DeepSeek V4.1
Flash, with Luna automation and Astra read-only review (no actionable findings).
Five source/test files are integrated into the main checkout, uncommitted. No
supervisor code repairs were needed. Date-only URL bounds resolve to city-local
midnight, while API/cache bounds remain full ISO instants. Exact midnight values
compact only when they round-trip without losing precision or fold identity.
Main-checkout verification: 144 frontend tests, TypeScript/production build, and
diff checks pass. The 33 focused date-only tests also pass in the worker under
both UTC and New York; the existing bundle-size warning remains. No deployed
browser verification or deployment was performed. Original candidate and logs:
`.pino/worktrees/date-only-deepseek` and `.pino/date-only-implementation/`.

## Existing contract and likely touchpoints

The preceding city SPA slice is documented in `docs/web-routing-cities-spa-brief.md`; city routing decisions are in `docs/web-routing-cities.md`. Current code already provides a registry-resolved city route with canonical internal ID `lt/vilnius`, aliases and entry redirects in `web/src/cityRoutes.ts` and `web/src/routes/CityRoute.tsx`, and city-scoped event requests/cache keys in `web/src/api.ts` and `web/src/routes/EventRoute/EventRoute.tsx`.

The main implementation seam is `web/src/eventFilterUrl.ts`: `parseInstant` currently accepts only explicit-offset full ISO timestamps, and `eventFiltersToSearchParams` always writes UTC ISO strings. Extend that boundary to accept date-only bounds in the selected city timezone and serialize city-local exact midnight compactly. Keep request serialization in `web/src/api.ts` as full `toISOString()` values. The route controls timezone through `parseEventFilterParams(..., timeZone)` and currently calls the URL serializer without a timezone; thread the resolved city timezone through every relevant parse/serialize/normalization path in `EventRoute.tsx`. Preserve `web/src/timezone.ts` as the shared explicit-zone conversion utility.

Likely tests: `web/src/eventFilterUrl.test.ts` for parser, serializer, normalization and interval semantics; `web/src/routes/CityRoute.test.tsx` for aliases, entry redirects and city-zone integration; and `web/src/routes/EventRoute/EventRoute.test.tsx` for filter editing/history behavior. Existing city/timezone coverage is substantial and should be adapted, not removed.

## Required behavior

### Routes and generated links

- Use `/vilnius` as the default generated browse URL and as the destination for entry/legacy redirects `/`, `/lt`, `/event`, and `/event/`.
- Both `/vilnius` and `/lt/vilnius` continue rendering the same feed, preserving whichever form the visitor requested. Do not redirect one alias to the other.
- Internal city ID remains `lt/vilnius`; event API query identity and cache identity continue to use that ID, never the path spelling.
- Preserve query parameters and hash on client-side replacements. Existing normalization, history behavior, and reserved route handling remain intact.
- Do not modify SEO canonical metadata or claim these SPA redirects are HTTP redirects.

### Date-only query values

- Accept strict `YYYY-MM-DD` values for `date_from` and `date_to`, with supported years 2 through 9998. Validate actual Gregorian dates, including leap days; reject rolled dates, malformed widths, year 0000/0001, and out-of-range years using the existing invalid-bound fallback behavior.
- Resolve a valid date-only bound as midnight in the resolved route city's IANA timezone. Date-only syntax has no embedded zone. `date_to` remains an exclusive upper bound.
- Continue accepting the existing full ISO instant syntax only when `T` is present and the value has an explicit `Z` or numeric offset. Preserve its resolved instant at the existing millisecond precision, including seconds and a later occurrence during a DST fold. Do not introduce nanosecond precision or change existing fractional-second parsing. Timezone-less full timestamps remain invalid.
- Serialize an instant as `YYYY-MM-DD` only when converting it to a city-local date and parsing that date-only value back in the same city timezone round-trips to the identical instant. Otherwise serialize the full UTC ISO instant. This avoids shortening a later occurrence of a hypothetical repeated midnight. A date-only value whose local midnight does not exist is invalid and follows ordinary invalid-bound fallback; do not shift it to another wall time.
- The supported year bounds apply to the resolved UTC instant, consistent with current behavior. A date-only value near a year edge can therefore resolve outside the supported UTC years and fall back.
- API requests continue carrying resolved full ISO instants. Query/cache identity remains based on resolved instants, not the original spelling (`2026-06-01` and its equivalent explicit instant share identity).
- Preserve the default 30 city-calendar-day window, 370 elapsed-day absolute interval cap, filtering rules, unrelated query keys, hash, replace/push semantics, and normalization behavior.

## Acceptance gates

Add or adapt tests proving:

1. `/`, `/lt`, `/event`, `/event/` replace to `/vilnius`; retain query/hash; both city aliases remain at their requested path and resolve to `lt/vilnius`.
2. Generated default browse links use `/vilnius`; no SEO metadata behavior changes.
3. Date-only `date_from` and `date_to` resolve to Vilnius-local midnight, including under `TZ=UTC` and `TZ=America/New_York`. Include `2026-10-25` in Vilnius and verify the date-only full-day interval is 25 hours because of the DST transition.
4. Real-date validation covers invalid month/day, leap day acceptance and rejection, supported-year edges after timezone resolution, invalid year bounds, and a zone/date where midnight is nonexistent (ordinary invalid-bound fallback, no silent shift).
5. Full timestamps with `Z` and offsets remain supported and retain precise instants, including arbitrary seconds/milliseconds and an explicit later fall-back occurrence; timestamps without zone suffix remain rejected.
6. A date-only URL that already represents resolved midnight does not repeatedly normalize/navigate. Non-midnight values normalize to UTC ISO; unrelated params/hash remain unchanged.
7. Requests still send full ISO instants and share city query/cache identity across alias spellings.
8. Existing default-window, 370-day cap, date_to exclusivity, Back/Forward, Reset, text replace, discrete push, and combined From/To update semantics remain covered.

Run `bun run test` and `bun run build` from `web/`, plus `git diff --check`. Run the new city-date tests directly with Vitest under both `TZ=UTC` and `TZ=America/New_York` (the normal test script pins Vilnius). Do not change dependencies to accomplish this.

## Boundary decisions and implementation checks

- **Invalid date-only bound fallback:** existing behavior independently defaults invalid/missing bounds and may then substitute the default end if the interval is unsafe. Keep this established resolver behavior rather than introducing a new error UI; confirm tests reflect it.
- **Date-only end semantics at DST:** resolve both date-only values independently to city-local midnight, then apply the existing 370-day elapsed-time cap. Thus a local calendar day can span 23, 24, or 25 elapsed hours; do not reinterpret the cap as calendar-day count.
- **Serialization policy:** compact only when a city-local date-only parse round-trips to the exact instant. This is intentional canonical URL normalization; ensure it does not change resolved request/cache identity.
- **Generated-link inventory:** current redirects live in `CityRoute`, while ordinary filter navigation retains current pathname. Confirm all links considered “default generated browse links” are covered; do not rewrite explicit user-selected `/lt/vilnius` paths.

## Out of scope

No backend or HTTP routing changes, server redirects/status codes, new city registry entries, public event URLs, canonical metadata/SEO changes, dependencies, migrations, infrastructure, data access, commits, or progress-log edits.
