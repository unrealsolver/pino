# Pino web routing, rendering, and UX architecture review

Review saved: 2026-09-23. This document records an architectural proposal, not an approved implementation plan. Repository observations and external documentation reflect the review at the time it was written.

My recommendation is **a list-first experience with modest inline expansion, independently addressable event pages, and server-rendered public content**. Start with the same single-column interaction on mobile and desktop. Add a desktop detail panel only if usage supports it.

The main assumption I would challenge is that a separate event URL necessarily makes browsing heavier. A URL identifies content; it does not dictate whether that content appears inline, beside a list, or on a separate screen.

I reviewed the current frontend, API, data model, and deployment documentation. This is an architectural review; I haven’t changed implementation files.

**Your UX direction is plausible, but several claims need qualification.**

| Proposal or claim | My assessment |
|---|---|
| Location belongs in the URL | Yes. It makes browsing predictable, shareable, and independently discoverable. |
| SSR is needed for indexing | Useful, but request-time SSR is only one solution. Prerendered HTML also works. Google can render JavaScript, but other crawlers may not. |
| The master list should not be server-rendered | Too absolute. Avoid rendering the entire personalized feed, but consider rendering a useful initial public listing. |
| Event details are secondary | Likely true for returning browsers; potentially false for visitors arriving through search or a shared link. |
| Separate detail navigation is poor on mobile | Often caused by lost position, slow loading, and bad Back behavior. A focused page can work very well on mobile. |
| Modals are unsuitable | A reasonable product decision here. Long descriptions and schedules are awkward overlay content. |
| Desktop needs two panels | Optional. A useful single column is a valid desktop design. |
| Swipeable cards might help | Worth exploring for another discovery mode, but I would not make them the primary browsing model. |
| Users should spend 80% of their time in the list | A hypothesis to test, not a success metric by itself. |

Google explicitly recommends server rendering or prerendering while acknowledging JavaScript rendering support. This supports delivering useful HTML, without requiring any particular frontend framework. [Google’s JavaScript SEO guidance](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)

**I would design three levels of information.**

1. **The list answers “Is this interesting and practical?”** Show title, concise description, date/time, venue, useful imagery, and price or booking constraints when available. Allow the main action directly from the row when appropriate.
2. **A small inline expansion answers one additional question.** For example, reveal the next few performances, a longer description, or attendance information. Keep its extent predictable.
3. **The full event page supports deliberate investigation.** Full schedule, original source text, gallery, provenance, and secondary metadata belong here.

This gives users a reason to stay in the list without forcing the list to contain everything.

The boundary matters: expanding a row into several screens of text and images damages scanning and makes finding the next event harder. Inline expansion should be a preview, not an entire detail page embedded between two rows.

Your current list is virtualized, which makes large expanding rows more demanding: changing heights, image loading, unmounting, focus, and scroll anchoring all need care. That is a concrete reason to keep expansion limited.

Swipeable cards would favor sequential exploration over comparison. My hypothesis is that a dated event list benefits more from seeing several alternatives together. Horizontal swiping could still work inside an image gallery, with visible controls.

**Give the routes clear, stable meanings.**

A reasonable starting point is:

| Route | Meaning |
|---|---|
| `/` | Location entry point, with real city links |
| `/lt/vilnius` | Public Vilnius listing |
| `/lt/vilnius?from=2026-09-25&category=music` | Shareable filtered listing |
| `/events/{stable-id}/{optional-slug}` | Canonical event page |

Here, `lt` explicitly means **country**, not interface language. Those concepts should remain separate. I would normalize casing to lowercase.

I slightly prefer global event URLs because correcting a location, changing venues, or featuring an event in several nearby-city feeds would not change its identity. Nesting events under `/lt/vilnius/events/...` is also defensible if each event reliably belongs to one city; it requires a redirect policy when that assignment changes.

For `/`, remembered city selection is a good reason for client-side replacement navigation. With no preference, show a small location selector or an explicit default. Keep actual city links in the initial HTML. Never override an explicitly requested city or event because of inferred location.

Google warns that location-dependent content can be incompletely crawled; explicit URLs provide a more dependable foundation. [Locale-adaptive crawling guidance](https://developers.google.com/search/docs/specialty/international/locale-adaptive-pages)

**Keep lightweight expansion and navigation distinct initially.**

My first implementation would use:

- A “More” button that expands a bounded preview without changing the URL.
- A real event-title link that opens the full event route.
- Back navigation that restores filters, position, and the previously focused row.
- A direct event visit that immediately displays the event, with a clear “Events in Vilnius” link.

On mobile, full details use the normal document scroll. No modal, no internal scrolling container, no requirement to reconstruct a whole list before showing the event.

On desktop, start with the same behavior. If users frequently inspect several events in succession, introduce an optional side panel.

A more ambitious alternative is **contextual routing**: clicking an event updates its canonical URL while displaying details beside or within the existing list; opening that same URL directly shows the standalone page. This is viable, but adds history, refresh, focus, and restoration complexity. I would adopt it only after the simpler interaction shows a real problem.

Whichever presentation you choose, store public filters in the URL and browsing restoration state in session/history state. For your virtual list, restore an occurrence/day anchor plus its offset where possible; a raw pixel position is fragile when content changes.

**I would server-render some city content as well as event pages.**

The full interactive master list includes filters, hidden-event preferences, virtualization, and potentially hundreds of occurrences. That whole system does not need to run on the server.

A public city page can nevertheless return:

- Its title and location context.
- A bounded set of upcoming event summaries with genuine links.
- A crawlable path to additional events where needed.
- Useful content before JavaScript loads.

The client can then provide filtering and richer browsing. This public listing should be part of the actual user experience, with a stable handoff into the interactive list.

For an event route, return meaningful visible content in the initial HTML: title, description, dates, venue, images, source link, canonical URL, and sharing metadata. Structured data complements that content; it does not replace it.

There is also a relevant distinction between **ordinary indexing** and **Google’s special event search experience**. Google requires unique event URLs and pages focused on individual events for the latter. Its currently documented supported regions do **not** include Lithuania, so I would not justify the architecture primarily through promised event-rich-result visibility. [Google’s event documentation](https://developers.google.com/search/docs/appearance/structured-data/event)

Indexing also does not guarantee traffic. Pino’s aggregation, schedule clarity, and location filtering need to offer useful value beyond repeating source text.

**The current data model has two prerequisites more consequential than the router choice.**

First, establish durable public event identity. The UI currently identifies events through `refinement_id`, but refinements receive generated IDs and can be deleted and replaced during refinement. Publishing those IDs directly risks breaking links when content is reprocessed. See [refinement construction](../packages/pino-core/src/pino_core/refinement.py) and [replacement behavior](../packages/pino-core/src/pino_core/storage.py).

Define an event identity that survives extraction changes. Keep occurrences separate from the parent event, and decide how duplicate source records map to that identity. A repeat performance and a multi-day continuous event also need different schedule semantics.

Second, location needs structured meaning. The current refinement has a free-text `location`, and the listing API has no city filter. `/lt/vilnius` should correspond to an explicit city identifier and defined geographic scope. Give the city a timezone as well: “today in Vilnius” should remain consistent when someone browses from another timezone.

Add a detail endpoint that works independently of the current list’s date window, filters, and result limit. A shared event must remain accessible even when it is absent from today’s feed.

**For rendering technology, there are three credible options.**

| Approach | Benefit | Cost |
|---|---|---|
| React Router framework rendering with SSR | Shared React/Mantine components across initial HTML and client navigation | Adds a JavaScript server runtime and changes deployment |
| Python-rendered public pages plus the existing React application | Fits the existing Python service; supports fresh HTML | Two presentation implementations and a more deliberate client handoff |
| Prerendered city/event pages | Static serving; no frontend server runtime | Requires regeneration tied to content updates and reliable expiry/cancellation handling |

For the product direction you describe, **I lean toward React Router framework rendering if an additional runtime is acceptable**. You already use React Router; Python can continue owning event data and business logic. Framework rendering supports SSR, prerendering, and client-loaded portions of the UI. [React Router rendering strategies](https://reactrouter.com/start/framework/rendering)

That is a deliberate infrastructure change: the [current deployment](production.md) serves static frontend files through Caddy alongside Python. It is not merely enabling a Vite option.

If preserving that deployment is a strong priority, Python-rendered public pages are a reasonable first choice. Prerendering is attractive only with a dependable content-publication workflow; rebuilding pages solely on software releases would leave event information stale.

I would implement durable identities and city semantics first, then canonical event pages and a small rendered city listing, then bounded expansion with reliable Back restoration. Test the result on a real phone with realistic descriptions and schedules before adding panels or contextual routing.

Measure whether people find an event, understand its timing, and reach their intended action. Low detail-page usage can indicate a successful list—or insufficient interest. The useful evidence is whether users accomplish their task with little effort.
