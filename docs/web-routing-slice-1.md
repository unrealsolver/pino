# Slice 1: shareable list filters

Implement this slice only. Read `AGENTS.md` and the recent entries of
`docs/progress.md`. The broader `docs/web-routing-plan.md` is context, not scope.

## Outcome

The existing `/event/` list restores its public filters from the URL on direct entry,
reload, and browser Back/Forward. Editing filters updates the URL and fetches the same
values. Preserve the current visual design and immediate filtering (no Apply button).

## Query contract

Use `date_from`, `date_to`, repeated `category`, `min_score`, and `q`, matching API
names. Serialize dates as UTC ISO instants. Accept ISO datetime inputs with an explicit
`Z` or numeric offset; reject date-only, timezone-less, impossible, or unparseable
values. Missing/invalid `date_from` uses today's browser-local morning (existing
behavior); missing/invalid `date_to` uses `defaultDateTo(resolvedDateFrom)`.
If end precedes start or the absolute interval exceeds 370 days, reset the end to
`defaultDateTo(resolvedDateFrom)`. Keep supported date years within 2..9998 so the API
does not receive its rejected boundary years.

Boundary clarification: check supported years after conversion to UTC as well as
calendar validity before conversion. If a start cannot produce a valid default end
(for example late December 9998), treat that start as invalid and use the ordinary
current default window. Never fall back into year 9999 or serialize an invalid Date.

Score must be a finite number in [0,1], otherwise use 0. Trim category strings, remove
empty/duplicate entries, sort them for stable serialization, and cap at 64. Preserve
unknown category names for the existing API validation; do not discard them while
metadata loads. Preserve query text including spaces, capped at 200 characters; the
existing API request layer may trim it. For repeated scalar keys, use the first value.

Apply the category cap after trimming, deduplication, and sorting.

Serialize resolved date bounds explicitly after a user filter action so a shared
filtered URL retains that date window. Omit empty `q`, zero `min_score`, and no categories.
Preserve unrelated query parameters and the fragment. Do not rewrite/normalize the URL
merely on mount; parse safely and normalize owned parameters on the next user action.
Reset removes only the five owned keys and returns to current default filters.

## State and history

Use React Router's location/navigation facilities. Keep one authoritative applied
filter state; avoid two opposing effects that copy form state into the URL and back.
Retain Mantine form where it helps; a small controlled form API is also acceptable.
Do not mutate React Router's shared search-params object in place.

Text edits use replace navigation to avoid one history entry per character. Category,
score, date, Reset, and Next month actions push one entry when the effective state
changes. Equivalent/no-op actions must not add entries. Back/Forward must restore
controls and the API query without being overwritten by a stale form update. Do not
request default filters before reading a valid initial URL. A single user action that
changes both date bounds must navigate once.

If effective filters do not change but an action needs to normalize the URL or Reset
needs to remove owned keys, replace the current entry. If neither filters nor URL
change, do nothing. This also applies to semantically equivalent category orderings.

Preserve the existing From behavior (reset To to one default window after the new
From), To fallback behavior, and Next month behavior (extend current To by one default
window). Enforce the same safe interval rules on UI actions. Hidden IDs and show-hidden
stay in local storage and must never be serialized into public URLs.

## Scope and verification

Allowed implementation area: `web/src/`. Do not change dependencies, lockfiles, backend,
schema, route paths, deployment, analytics, event identities, city semantics, CSS, or
virtualization. No new SSR, detail pages, expansion, scroll restoration, or debounce
requirements. Preserve unrelated files. Do not commit, push, or access live services.

Add meaningful tests for parsing/serialization edge cases and router-integrated
behavior: initial URL controls/request, user edits, Back/Forward, Reset preserving
unrelated params/hash, Next month, and no-op history. Mock the network and virtual list
where useful; do not mock away the router synchronization being tested. Test tricky
date cases including a valid leap day and an invalid calendar date. Run:

```sh
cd web
bun run test
bun run build
```

Run `git diff --check` from the worktree root. Finish with changed-file summary, check
results, and any limitations. Do not update the progress log during this comparison;
the supervisor records the selected result once. Do not read other candidate worktrees.
