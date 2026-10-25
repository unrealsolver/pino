export type EventItem = {
  images?: string[];
  refinement_id: string;
  occurrence_id: string;
  title: string;
  text?: string;
  source: string;
  url: string | null;
  location: string | null;
  city_id?: string | null;
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

export type City = {
  id: string;
  country_code: string;
  slug: string;
  name: string;
  timezone: string;
};

export type CityListResponse = {
  cities: City[];
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

export type EventQueryKey = ["events", string, SerializedEventFilters];

export const CITIES_QUERY_KEY = ["cities"] as const;

export function serializeEventFilters(filters: EventFilters): SerializedEventFilters {
  return {
    categories: filters.categories,
    minScore: filters.minScore,
    query: filters.query,
    dateFrom: filters.dateFrom.toISOString(),
    dateTo: filters.dateTo?.toISOString() ?? null
  };
}

/** The canonical city id is part of the key; short and qualified routes share it. */
export function eventQueryKey(cityId: string, filters: EventFilters): EventQueryKey {
  return ["events", cityId, serializeEventFilters(filters)];
}

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail || `Request failed with ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function fetchCities(
  options: { signal?: AbortSignal } = {}
): Promise<CityListResponse> {
  const response = await fetch("/api/cities", {
    headers: { Accept: "application/json" },
    signal: options.signal
  });
  return readJson<CityListResponse>(response);
}

export async function fetchEvents(
  cityId: string,
  filters: EventFilters,
  options: { signal?: AbortSignal } = {}
): Promise<EventListResponse> {
  const serializedFilters = serializeEventFilters(filters);
  const params = new URLSearchParams();
  params.set("city", cityId);
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
  return readJson<EventListResponse>(response);
}
