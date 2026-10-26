import type { EventFilters } from "./api";
import { defaultDateTo, todayMorning } from "./eventUtils";
import { dateKeyInTimeZone, defaultTimeZone, wallClockToInstant } from "./timezone";

/** Public URL query keys owned by the event list filters. */
export const EVENT_FILTER_PARAM_KEYS = ["date_from", "date_to", "category", "min_score", "q"] as const;

export const MAX_EVENT_FILTER_CATEGORIES = 64;
export const MAX_EVENT_FILTER_QUERY_LENGTH = 200;
export const MAX_EVENT_FILTER_RANGE_DAYS = 370;
export const MIN_SUPPORTED_DATE_YEAR = 2;
export const MAX_SUPPORTED_DATE_YEAR = 9998;

const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;
const MAX_EVENT_FILTER_RANGE_MS = MAX_EVENT_FILTER_RANGE_DAYS * MILLISECONDS_PER_DAY;

// ISO datetime with an explicit zone: `Z` or a numeric `±HH:MM` offset. Timezone-less
// strings are intentionally rejected.
const INSTANT_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})$/;

// Strict city-local calendar date. Widths are exact, so `2026-6-1` is not accepted.
const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Parses the public filter query string into resolved filter state. Invalid or
 * missing values fall back to the same defaults the list used before URLs existed.
 */
export function parseEventFilterParams(
  params: URLSearchParams,
  now: Date = new Date(),
  timeZone: string = defaultTimeZone()
): EventFilters {
  const { dateFrom, dateTo } = resolveEventWindow(
    parseBound(params.get("date_from"), timeZone),
    parseBound(params.get("date_to"), timeZone),
    now,
    timeZone
  );
  return {
    categories: normalizeCategories(params.getAll("category")),
    minScore: normalizeScore(params.get("min_score")),
    query: normalizeQuery(params.get("q")),
    dateFrom,
    dateTo
  };
}

/**
 * Serializes resolved filters into a fresh query string, rewriting only the five
 * owned keys and preserving every unrelated parameter.
 *
 * A bound is written as a city-local `YYYY-MM-DD` only when that date parses back
 * to the identical instant in the same timezone; everything else stays full UTC ISO.
 */
export function eventFiltersToSearchParams(
  filters: EventFilters,
  base?: URLSearchParams,
  timeZone: string = defaultTimeZone()
): URLSearchParams {
  const params = removeEventFilterParams(base);
  params.set("date_from", serializeBound(filters.dateFrom, timeZone));
  if (filters.dateTo) {
    params.set("date_to", serializeBound(filters.dateTo, timeZone));
  }
  for (const category of filters.categories) {
    params.append("category", category);
  }
  if (filters.minScore > 0) {
    params.set("min_score", String(filters.minScore));
  }
  if (filters.query) {
    params.set("q", filters.query);
  }
  return params;
}

/** Removes every owned filter key while leaving other parameters untouched. */
export function removeEventFilterParams(base?: URLSearchParams): URLSearchParams {
  const params = new URLSearchParams(base);
  for (const key of EVENT_FILTER_PARAM_KEYS) {
    params.delete(key);
  }
  return params;
}

export function hasEventFilterParams(params: URLSearchParams): boolean {
  return EVENT_FILTER_PARAM_KEYS.some((key) => params.has(key));
}

/**
 * True when the resolved state would serialize to a different owned query than the
 * current one, i.e. the URL still needs normalizing (explicit bounds, canonical order,
 * omitted empty values).
 */
export function eventFilterParamsNeedNormalization(
  filters: EventFilters,
  params: URLSearchParams,
  timeZone: string = defaultTimeZone()
): boolean {
  return eventFiltersToSearchParams(filters, params, timeZone).toString() !== params.toString();
}

/** True when the two filter states resolve to the same request. */
export function eventFiltersEqual(a: EventFilters, b: EventFilters): boolean {
  return (
    a.dateFrom.getTime() === b.dateFrom.getTime() &&
    (a.dateTo?.getTime() ?? null) === (b.dateTo?.getTime() ?? null) &&
    a.minScore === b.minScore &&
    a.query === b.query &&
    sameStrings(a.categories, b.categories)
  );
}

/**
 * Applies the same safe bounds on UI actions that parsing applies to URLs:
 * supported UTC years, canonical category/score/query shapes, and the 370-day window.
 */
export function normalizeEventFilters(
  filters: EventFilters,
  timeZone: string = defaultTimeZone()
): EventFilters {
  const { dateFrom, dateTo } = resolveEventWindow(
    filters.dateFrom,
    filters.dateTo ?? null,
    new Date(),
    timeZone
  );
  return {
    categories: normalizeCategories(filters.categories),
    minScore: normalizeScore(filters.minScore),
    query: normalizeQuery(filters.query),
    dateFrom,
    dateTo
  };
}

/**
 * Resolves a start/end pair into a supported window. Candidates are validated after
 * conversion to UTC; a start that cannot produce a valid default end (for example late
 * December 9998) is treated as invalid and the ordinary current default window is used.
 */
function resolveEventWindow(
  candidateFrom: Date | null,
  candidateTo: Date | null,
  now: Date,
  timeZone: string
): { dateFrom: Date; dateTo: Date } {
  const defaultFrom = todayMorning(now, timeZone);
  const dateFrom = isSupportedInstant(candidateFrom) ? candidateFrom : defaultFrom;
  if (!isSupportedInstant(defaultDateTo(dateFrom, timeZone))) {
    return { dateFrom: defaultFrom, dateTo: defaultDateTo(defaultFrom, timeZone) };
  }
  const defaultEnd = defaultDateTo(dateFrom, timeZone);
  let dateTo = isSupportedInstant(candidateTo) ? candidateTo : defaultEnd;
  if (isUnsafeInterval(dateFrom, dateTo)) {
    dateTo = defaultEnd;
  }
  return { dateFrom, dateTo };
}

/**
 * A bound is either a strict city-local date or a full ISO instant with an explicit
 * zone. Date-only values have no embedded zone, so the resolved route timezone is
 * required to place them.
 */
function parseBound(value: string | null, timeZone: string): Date | null {
  if (!value) {
    return null;
  }
  return DATE_ONLY_PATTERN.test(value)
    ? parseDateOnly(value, timeZone)
    : parseInstant(value);
}

/**
 * Resolves `YYYY-MM-DD` to the first instant of that calendar date in the city
 * timezone. Nonexistent midnights are invalid rather than advanced by the DST gap.
 */
function parseDateOnly(value: string, timeZone: string): Date | null {
  const match = DATE_ONLY_PATTERN.exec(value);
  if (!match || match[0] !== value) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < MIN_SUPPORTED_DATE_YEAR || year > MAX_SUPPORTED_DATE_YEAR) {
    return null;
  }
  if (!isRealWallClock(year, month, day, 0, 0, 0, 0)) {
    return null;
  }
  return wallClockToInstant(
    { year, month, day, hour: 0, minute: 0, second: 0, millisecond: 0 },
    timeZone
  );
}

/** Compact a bound only when the date-only form round-trips to the exact instant. */
function serializeBound(instant: Date, timeZone: string): string {
  const key = dateKeyInTimeZone(instant, timeZone);
  const roundTrip = parseDateOnly(key, timeZone);
  return roundTrip?.getTime() === instant.getTime() ? key : instant.toISOString();
}

function parseInstant(value: string | null): Date | null {
  if (!value) {
    return null;
  }
  const match = INSTANT_PATTERN.exec(value);
  if (!match) {
    return null;
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = match[6] ? Number(match[6]) : 0;
  const millisecond = match[7] ? Number(`${match[7]}000`.slice(0, 3)) : 0;
  const offset = match[8];
  if (!isRealWallClock(year, month, day, hour, minute, second, millisecond)) {
    return null;
  }
  if (offset !== "Z") {
    const offsetHours = Number(offset.slice(1, 3));
    const offsetMinutes = Number(offset.slice(4, 6));
    if (offsetHours > 23 || offsetMinutes > 59) {
      return null;
    }
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Rejects rolled-over calendar values like 2026-02-30 that `Date` silently accepts. */
function isRealWallClock(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  second: number,
  millisecond: number
): boolean {
  const wall = new Date(0);
  wall.setUTCFullYear(year, month - 1, day);
  wall.setUTCHours(hour, minute, second, millisecond);
  return (
    wall.getUTCFullYear() === year &&
    wall.getUTCMonth() === month - 1 &&
    wall.getUTCDate() === day &&
    wall.getUTCHours() === hour &&
    wall.getUTCMinutes() === minute &&
    wall.getUTCSeconds() === second &&
    wall.getUTCMilliseconds() === millisecond
  );
}

/** Supported years are checked on the resolved instant, i.e. after UTC conversion. */
function isSupportedInstant(value: Date | null): value is Date {
  if (!value || Number.isNaN(value.getTime())) {
    return false;
  }
  const year = value.getUTCFullYear();
  return year >= MIN_SUPPORTED_DATE_YEAR && year <= MAX_SUPPORTED_DATE_YEAR;
}

function isUnsafeInterval(dateFrom: Date, dateTo: Date): boolean {
  const span = dateTo.getTime() - dateFrom.getTime();
  return span < 0 || span > MAX_EVENT_FILTER_RANGE_MS;
}

function normalizeCategories(values: readonly string[]): string[] {
  const unique = new Set<string>();
  for (const value of values) {
    const trimmed = value.trim();
    if (trimmed) {
      unique.add(trimmed);
    }
  }
  // Trim, de-duplicate, sort, then cap: the cap keeps the alphabetically first names.
  return [...unique].sort().slice(0, MAX_EVENT_FILTER_CATEGORIES);
}

function normalizeScore(value: string | number | null | undefined): number {
  if (value === null || value === undefined) {
    return 0;
  }
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
    return 0;
  }
  return parsed;
}

function normalizeQuery(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  return value.slice(0, MAX_EVENT_FILTER_QUERY_LENGTH);
}

function sameStrings(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}
