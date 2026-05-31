# Source Integration Backlog

This document tracks source integrations worth adding to Pino. It focuses on sources that improve discovery for current goals: meeting interesting people in Vilnius, metal music, electronic music, synth-adjacent events, volunteering, and community gatherings.

## Current Source Types

- `static_yaml`: local fixture/sample records.
- `kaveikti`: parses kaveikti.lt Vilnius event listing pages.
- `telegram_channel`: fetches recent Telegram channel messages through Telethon.
- `vilnius_events`: parses vilnius-events.lt listing pages.

## Recommended Priority

1. `meetup`
   - URL: `https://www.meetup.com/find/lt--vilnius/`
   - Why: high signal for social, tech, language, hobby, workshop, and casual community events.
   - Fit: `meet_people`, `volunteering_community`, occasional music/synth-adjacent gatherings.
   - Notes: already listed as an initial source in the README, but no adapter exists yet.

2. Ticketing platforms
   - Candidates: `fienta`, `bilietai.lt`, `kakava.lt`.
   - Why: strong coverage for concerts, festivals, and paid cultural events.
   - Fit: `metal_music`, `electronic_music`, broader cultural discovery.
   - Notes: start with one adapter where listing HTML is stable, then generalize if the others have similar structure.

3. `resident_advisor`
   - URL: `https://ra.co/events/lt/vilnius`
   - Why: likely the best focused source for electronic music, club nights, DJs, and venue-linked nightlife.
   - Fit: `electronic_music`, possibly `meet_people`.
   - Notes: useful even with sparse listings because matches are high relevance.

4. Generic venue page adapter
   - Candidate source type names: `html_events`, `json_ld_events`, or `venue_events`.
   - Why: many useful venues publish their own event pages, but one adapter per venue would create too much integration churn.
   - Candidate venues:
     - Lukiškių kalėjimas 2.0
     - Loftas
     - Kablys / Club Kablys
     - SODAS 2123
     - Vasaros Terasa
     - Gallery 1986
     - Elastica
     - Narauti / Red Cat
   - Fit: concerts, electronic music, cultural salons, workshops, and niche social events.
   - Notes: prefer JSON-LD or stable HTML selectors before source-specific scraping.

5. Volunteering and community sources
   - Candidates:
     - Open House Vilnius volunteering
     - Skamba skamba kankliai volunteering/events
     - GameOn volunteering
     - Local NGO/community calendars where listings are public and stable
   - Why: directly supports the broadened `meet_people` goal and tends to produce natural conversation settings.
   - Fit: `meet_people`, `volunteering_community`.
   - Notes: these may be seasonal; adapter should tolerate empty or stale pages.

6. Songkick or Bandsintown-style concert discovery
   - Candidate: Songkick Vilnius listings.
   - Why: useful for artist/genre discovery and metal alerts that may not appear on local general event portals.
   - Fit: `metal_music`, broader concert discovery.
   - Notes: check access limits and terms before implementation.

7. Facebook public events/groups
   - Why: likely high coverage for niche community events, workshops, and small gatherings.
   - Fit: `meet_people`, `volunteering_community`, niche concerts.
   - Notes: postpone until cleaner public web, Telegram, ticketing, and venue sources are useful. Login/API/scraping behavior can be brittle.

## Implementation Notes

- Follow [Source Adapter Spec](source-spec.md) when adding repo-local custom integrations.
- Prefer source adapters that return raw generic `Record` objects with source-native payload fields useful for audit and later reprocessing.
- Normalize dates, locations, summaries, and taxonomy scores in the reusable refinement layer rather than inside adapters.
- Keep source-specific parsing in `pino-integration`; keep ranking, digest, and chat retrieval in `pino-core`.
- Add fixtures for each parser before enabling a live source in example config.
- Cross-source deduplication should be implemented before many overlapping event sources are enabled by default.
