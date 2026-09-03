# Refinement Layer Proposal

This document describes the implemented foundation and the remaining direction.
The goal is to keep source capture lossless and cheap while making normalized
data reusable across different Pino profiles.

## Direction

Raw records and queryable refinements should have separate ownership:

- `records` capture what a source published.
- `refinements` contain normalized, queryable facts derived from a record.
- Pino applies private preferences when querying refinements.

Do not store normalized event fields partly in records and partly in
refinements. A structured HTML source and an unstructured Telegram message
should converge on the same refinement shape. The producer may differ:

- A deterministic extractor can refine source-provided structured data.
- An LLM can refine unstructured text.
- A later pass can classify or embed the normalized item.

## Lean Storage Shape

Keep `records` close to raw capture:

```text
records
  id
  source
  kind
  external_id
  fingerprint
  title
  text
  url
  published_at
  captured_at
  payload
  provenance
```

`payload` is allowed to preserve source-native data for inspection and future
reprocessing. It should not become a parallel normalized schema. In particular,
query code should not depend on normalized dates, locations, or categories in
record payloads.

`published_at` is the source-provided publication instant when known;
`captured_at` is when Pino first stored the record. Do not substitute one for the
other.

Use one lean refinement table:

```text
refinements
  record_id
  item_index
  schema_version
  taxonomy_version
  content_kind
  summary
  relevant_from
  relevant_to
  schedule (optional structured JSON)
  location
  category_scores (optional cached projection)
  embedding (optional dense vector)
  refiner
  refined_at
  debug (optional)
```

The stable identity is `(record_id, item_index)`. Most records produce one row
with `item_index = 0`. A message containing several events produces one row per
event. This avoids a separate `refined_items` table and avoids storing an
`is_multi_event` flag: multiple events are derived by counting refinement rows
for the same record.

Keep `content_kind` intentionally small:

```text
event
advertisement
announcement
non_event
unknown
```

Do not add boolean columns that repeat `content_kind`. `debug` may retain the
raw refiner response, parse warnings, or uncertain classifier output, but query
logic should not depend on ad hoc debug flags.

`location` is the event venue or useful human-readable place when extracted.
Do not store `location_scopes` in refinements. Geographic scope should be
derived from source metadata when possible. Add item-specific scope storage
only after real examples prove that source-level scope is insufficient.

## Query Model

Upcoming-event queries should read from `refinements`, not `records`.

- Filter by `content_kind = "event"`.
- Filter by `relevant_from` / `relevant_to` when known.
- Join the raw record for source, URL, and original text.
- Derive source-level geographic scope from source metadata.
- Apply Pino's private preference weights at query time.

Records without refinements remain visible in raw/debug views and pending-work
counts. They should not silently enter an upcoming-event query.

Relevant-record retrieval must avoid truncating candidates before compatibility
is computed. A small date-ordered slice can hide moderately compatible events
that appear later in the window. The current tool scans a larger bounded window,
then applies category filtering and score ordering. If a good option appears in
`records.list` but not `records.relevant`, debug in this order:

1. Does the record have a refinement row?
2. Is `content_kind` `event`?
3. Are `relevant_from` / `relevant_to` inside the requested window?
4. Are category scores present for the queried categories?
5. Was the candidate pool large enough before ranking?

This is separate from embeddings. Embeddings should improve semantic recall and
ranking after the basic refinement and candidate-generation gates are visible.

## Refinement Pipeline

Start with a small staged pipeline:

1. Capture the raw record and split compound sources into atomic records when needed.
2. Extract one normalized refinement for each atomic record.
3. Compute reusable category data for the refinement.
4. Query and rank refinements for the active Pino profile.

The extraction stage should return only normalized facts:

```json
{
  "content_kind": "event",
  "summary": "Open modular synth jam in Vilnius.",
  "schedule": null,
  "location": "Example venue"
}
```

If the model cannot reliably produce one item, it returns only
`{"error": "short reason"}`.

`schedule` is optional canonical temporal data. It describes only when an item
occurs; participation or availability semantics do not belong in it. Missing
schedule data is valid.

`relevant_from` and `relevant_to` are internal searchable-envelope fields derived
from `schedule`; the LLM never authors them. They remain null when an item has no
schedule and must not be displayed as occurrences. A valid schedule that produces
no occurrence in a requested window does not fall back to its broad envelope.

When an atomic source record describes repeated instances of the same event,
store one refinement with a `recurrence` schedule instead of one refinement per
date. Genuinely different events must be split upstream.

Schedule v1 is a versioned union of explicit occurrences and weekly recurrence.
Times are local wall times in the IANA `timezone`.

```json
{
  "version": 1,
  "timezone": "Europe/Vilnius",
  "kind": "occurrences",
  "occurrences": [
    {
      "start": "2026-06-01T18:30",
      "end": "2026-06-01T20:10"
    }
  ]
}
```

```json
{
  "version": 1,
  "timezone": "Europe/Vilnius",
  "kind": "recurrence",
  "frequency": "weekly",
  "from": "2026-06-02",
  "until": "2026-06-30",
  "rules": [
    {
      "weekdays": ["tuesday", "thursday"],
      "start": "18:00",
      "end": "19:30"
    }
  ]
}
```

`occurrences[].end` and recurrence `rules[].end` may be null. An end at or before
the start is on the following local day. Recurrence `from` and `until` are
inclusive local dates; `until: null` means unbounded. Each rule keeps weekdays
and its time together so different weekday/time combinations do not form an
accidental Cartesian product. Exceptional finite date lists should use explicit
occurrences in v1 rather than add a broader recurrence language.

The Web API should project schedules into per-occurrence display rows inside the
requested window while keeping the canonical refinement row as source of truth.
PostgreSQL may use a derived weekly multirange index as a lossy prefilter;
SQLite performs the same exact application-level expansion without that index.
The index is rebuildable and never canonical schedule data. Do not add a stored
occurrence relation unless measurements show it is necessary.

Projected Web API event rows should expose row identity separately from
canonical refinement identity:

```text
refinement_id  canonical refinement/event id
occurrence_id  stable projected row id
starts_at      projected/clipped occurrence start
ends_at        projected/clipped occurrence end, or null
relevant_from  canonical coarse envelope start
relevant_to    canonical coarse envelope end, or null
```

Frontend row keys should use `occurrence_id`. Event-level preferences and debug
actions should use `refinement_id` so hiding or rerunning a refinement applies
to all projected occurrences of the same event.

For a structured event source, use deterministic extraction where trustworthy.
For Telegram and other prose-heavy sources, use an LLM extraction pass.

After normalization and before persistence, a source may run deterministic QC.
The immutable `QCReport` is an in-memory stage result and is not added to the
LLM prompt. An error discards the generated item and persists only a minimal
`qc:rejected` tombstone refinement (`content_kind: unknown`, no summary or
schedule), so the raw record does not remain pending. A warning is reported but
allows the generated refinement through.

Afisha Vilnius enables `qc: afisha_vilnius`. Its `#Dmonth` tags are mandatory
schedule evidence using the publication year. Explicit occurrences must contain
all tagged dates and warn about additional dates. A recurrence only has to
produce an occurrence when probed on every tagged date.

Keep extraction separate from personalized ranking. A user's current goals
must not be embedded into reusable refinement rows.

## Taxonomy

Treat taxonomy as a versioned, additive projection rather than a permanent
ontology. Start with categories already proven useful by current goals and
source examples. Add specificity only when examples demonstrate that queries
need it.

Candidate seed categories include:

```text
social
metal_music
electronic_music
open_synth_jam
live_music
volunteering
community
workshop
theatre
pottery
dating
```

The exact initial list still needs a short review against captured data.

Compatibility rules:

- Never silently redefine the meaning of an existing category key.
- Add new categories without removing old keys.
- Record `taxonomy_version` with cached category scores.
- Treat a missing category score as "not computed", not as a confident zero.
- Recompute projections lazily when a query needs newer taxonomy keys.

Private Pino profiles can rank categories differently without changing stored
refinements. Ensure the cached projection covers the requested taxonomy keys
before ranking:

```python
rank = sum(profile_weights[key] * category_scores[key] for key in profile_weights)
```

## Embedding Models

Embedding models can help produce taxonomy vectors, but their native output is
not the small taxonomy vector itself.

An embedding model produces a dense semantic vector. Embed each normalized
refinement summary and each category description, then compute cosine
similarity. The resulting similarities form a small taxonomy projection:

```python
category_scores = {
    category.name: cosine_similarity(item_embedding, category.embedding)
    for category in taxonomy.categories
}
```

This is attractive because a new category usually requires embedding only its
description and recomputing similarities. Existing item embeddings remain
reusable.

However, cosine similarities are not calibrated multi-label probabilities.
Near categories such as `electronic_music`, `live_music`, and
`open_synth_jam` may overlap. Before relying on embedding-only classification,
compare it against a small labeled set of real captured items.

A pragmatic first version:

1. Use deterministic or LLM extraction for facts and summary.
2. Store one dense embedding per refinement row.
3. Compute and cache the versioned small taxonomy projection from embeddings.
4. Add an LLM taxonomy pass only for categories where measured embedding
   quality is insufficient.

With PostgreSQL available, `pgvector` is the natural place to store dense
refinement vectors next to relational data. Keep the relational gates explicit:
date window, `content_kind`, source provenance, and refinement status should
remain normal columns. Use vector search as candidate expansion or reranking,
not as the only way an event can enter consideration.

For local SQLite development, embeddings can still be stored as JSON for
inspection or small offline experiments. Use PostgreSQL + `pgvector` when
nearest-neighbor search becomes part of the normal query path.

References:

- [OpenAI vector embeddings guide](https://platform.openai.com/docs/guides/embeddings)
- [Sentence Transformers semantic textual similarity documentation](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)

## Current Status

Implemented:

1. `records` no longer own relevance dates.
2. `refinements` store reusable multi-item normalized output.
3. `pino refine` runs generic LLM refinement; `pino evaluate` is a temporary alias.
4. Telegram publication time remains raw payload metadata rather than event relevance.
5. Upcoming-event queries and digests read refinements.
6. Goal-specific evaluations no longer drive active queries.
7. Optional event schedules are stored on refinements and projected by the Web
   API into display occurrences with separate `refinement_id` and
   `occurrence_id` fields.

Remaining:

1. Add deterministic refinement shortcuts for trustworthy structured sources if
   LLM cost or quality measurements justify them.
2. Add a normalized display title or short summary for Web UI event rows. The
   refined item should provide an English display string with bounded length,
   no embedded dates, and no source/title garbage so the frontend does not have
   to show raw source titles when they are noisy or overly long.
3. Define query-time private profile weighting beyond explicit category filters.
4. Research using an embedding model to generate dense vectors for refined
   items and derive categories/category scores later from vector similarity or
   another projection step. The goal is to keep GPT-OSS-120b focused on
   extraction, normalization, and summaries instead of making it directly do
   the poorly scalable categorization/scoring task for every taxonomy version.
   Try local dense embeddings with Ollama `bge-m3`, then benchmark taxonomy
   projections on a labeled sample before making embeddings part of the default
   pipeline.
5. Remove inert legacy `records.relevant_from`, `records.relevant_to`, and
   `evaluations` columns/tables from existing SQLite files with an explicit
   migration if physical cleanup becomes worthwhile.
