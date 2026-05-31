# Refinement Layer Proposal

This document describes a target design, not the current schema. The goal is to
keep source capture lossless and cheap while making normalized data reusable
across different Pino profiles.

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
  captured_at
  payload
  provenance
```

`payload` is allowed to preserve source-native data for inspection and future
reprocessing. It should not become a parallel normalized schema. In particular,
query code should not depend on normalized dates, locations, or categories in
record payloads.

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

## Refinement Pipeline

Start with a small staged pipeline:

1. Capture the raw record.
2. Extract zero or more normalized refinement rows.
3. Compute reusable category data for each refinement row.
4. Query and rank refinements for the active Pino profile.

The extraction stage should return only normalized facts:

```json
{
  "content_kind": "event",
  "summary": "Open modular synth jam in Vilnius.",
  "relevant_from": "2026-06-05T16:00:00Z",
  "relevant_to": "2026-06-05T20:00:00Z",
  "location": "Example venue"
}
```

For a structured event source, use deterministic extraction where trustworthy.
For Telegram and other prose-heavy sources, use an LLM extraction pass.

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

For the current SQLite-scale dataset, store embeddings locally. A vector
database is not required until nearest-neighbor search volume proves otherwise.

References:

- [OpenAI vector embeddings guide](https://platform.openai.com/docs/guides/embeddings)
- [Sentence Transformers semantic textual similarity documentation](https://sbert.net/docs/sentence_transformer/usage/semantic_textual_similarity.html)

## Migration Outline

1. Add the `refinements` table and a refinement command or service.
2. Stop assigning Telegram publication time to event relevance fields.
3. Route deterministic event adapters through refinement creation.
4. Route Telegram records through LLM extraction.
5. Move upcoming-event queries and digests to refinements.
6. Remove `records.relevant_from` and `records.relevant_to`.
7. Replace goal-specific evaluations with query-time private profile ranking.

Do not remove the existing fields before the refinement query path is working.
