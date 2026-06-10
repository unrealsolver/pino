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

export type EventQueryKey = [
  "events",
  {
    categories: string[];
    minScore: number;
    query: string;
    dateFrom: string;
    dateTo: string | null;
  }
];

export function eventQueryKey(filters: EventFilters): EventQueryKey {
  return [
    "events",
    {
      categories: filters.categories,
      minScore: filters.minScore,
      query: filters.query,
      dateFrom: filters.dateFrom.toISOString(),
      dateTo: filters.dateTo?.toISOString() ?? null
    }
  ];
}

export async function fetchEvents(
  filters: EventFilters,
  options: { signal?: AbortSignal } = {}
): Promise<EventListResponse> {
  const params = new URLSearchParams();
  params.set("date_from", filters.dateFrom.toISOString());
  if (filters.dateTo) {
    params.set("date_to", filters.dateTo.toISOString());
  }
  for (const category of filters.categories) {
    params.append("category", category);
  }
  if (filters.minScore > 0) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters.query.trim()) {
    params.set("q", filters.query.trim());
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
