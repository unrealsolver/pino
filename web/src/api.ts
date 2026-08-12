export type EventItem = {
  refinement_id: string;
  occurrence_id: string;
  title: string;
  source: string;
  url: string | null;
  summary: string | null;
  location: string | null;
  starts_at: string;
  ends_at: string | null;
  relevant_from: string;
  relevant_to: string | null;
  category_scores: Record<string, number>;
  matching_score: number;
};

export type EventListResponse = {
  timezone: string;
  categories: string[];
  events: EventItem[];
};

export type EventFilters = {
  categories: string[];
  minScore: number;
  query: string;
  dateFrom: Date;
  dateTo: Date | null;
};

export type SerializedEventFilters = {
  categories: string[];
  minScore: number;
  query: string;
  dateFrom: string;
  dateTo: string | null;
};

export type EventQueryKey = ["events", SerializedEventFilters];

export function serializeEventFilters(filters: EventFilters): SerializedEventFilters {
  return {
    categories: filters.categories,
    minScore: filters.minScore,
    query: filters.query,
    dateFrom: filters.dateFrom.toISOString(),
    dateTo: filters.dateTo?.toISOString() ?? null
  };
}

export function eventQueryKey(filters: EventFilters): EventQueryKey {
  return ["events", serializeEventFilters(filters)];
}

export async function fetchEvents(
  filters: EventFilters,
  options: { signal?: AbortSignal } = {}
): Promise<EventListResponse> {
  const serializedFilters = serializeEventFilters(filters);
  const params = new URLSearchParams();
  params.set("date_from", serializedFilters.dateFrom);
  if (serializedFilters.dateTo) {
    params.set("date_to", serializedFilters.dateTo);
  }
  for (const category of serializedFilters.categories) {
    params.append("category", category);
  }
  if (serializedFilters.minScore > 0) {
    params.set("min_score", String(serializedFilters.minScore));
  }
  const query = serializedFilters.query.trim();
  if (query) {
    params.set("q", query);
  }

  const response = await fetch(`/api/events?${params.toString()}`, {
    headers: { Accept: "application/json" },
    signal: options.signal
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail || `Request failed with ${response.status}`);
  }
  return (await response.json()) as EventListResponse;
}
