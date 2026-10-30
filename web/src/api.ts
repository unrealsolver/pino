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

export type StatsRefinementItemCounts = {
  event: number;
  advertisement: number;
  announcement: number;
  non_event: number;
  unknown: number;
};

export type StatsRecordMetrics = {
  records_total: number;
  records_with_refinement_total: number;
  pending_records_total: number;
  oldest_pending_captured_at: string | null;
  latest_captured_at: string | null;
};

export type StatsRefinementMetrics = {
  refinement_items_total: number;
  refinement_items_by_kind: StatsRefinementItemCounts;
  event_items_total: number;
  last_refined_at: string | null;
};

export type StatsIngestionWeek = {
  week_start: string;
  week_end: string;
  starts_at: string;
  ends_at: string;
  is_partial: boolean;
  records: number;
  with_refinement: number;
  pending: number;
};

export type StatsSourceSyncAttempt = {
  state: "unfinished" | "success" | "failure";
  started_at: string;
  completed_at: string | null;
  fetched_count: number;
  inserted_count: number;
  duplicate_count: number;
  failure_stage: "fetch" | "store" | "cursor" | null;
};

export type StatsSourceSyncSuccess = {
  completed_at: string;
  fetched_count: number;
  inserted_count: number;
  duplicate_count: number;
};

export type StatsSourceSync = {
  state: "unknown" | "unfinished" | "success" | "failure";
  last_attempt: StatsSourceSyncAttempt | null;
  last_success: StatsSourceSyncSuccess | null;
};

export type StatsSource = {
  source: string;
  ingestion: StatsRecordMetrics;
  refinement: StatsRefinementMetrics;
  weeks: StatsIngestionWeek[];
  sync: StatsSourceSync;
};

export type StatsTotals = {
  ingestion: StatsRecordMetrics;
  refinement: StatsRefinementMetrics;
};

export type StatsCity = {
  city_id: string;
  country_code: string;
  slug: string;
  name: string;
  timezone: string;
  event_items_total: number;
  sources_with_event_items: number;
};

export type StatsResponse = {
  as_of: string;
  reporting_timezone: string;
  ingestion_time_basis: "captured_at";
  weeks: StatsIngestionWeek[];
  totals: StatsTotals;
  sources: StatsSource[];
  cities: StatsCity[];
  supported_cities_total: number;
  unassigned_city_event_items_total: number;
  unsupported_city_event_items_total: number;
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
export type StatsQueryKey = ["stats", number];

export const CITIES_QUERY_KEY = ["cities"] as const;

/** The reported week count is part of the key; the page uses one fixed window. */
export function statsQueryKey(weeks: number): StatsQueryKey {
  return ["stats", weeks];
}

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

export async function fetchStats(
  weeks: number,
  options: { signal?: AbortSignal } = {}
): Promise<StatsResponse> {
  const params = new URLSearchParams();
  params.set("weeks", String(weeks));

  const response = await fetch(`/api/stats?${params.toString()}`, {
    headers: { Accept: "application/json" },
    signal: options.signal
  });
  return readJson<StatsResponse>(response);
}
