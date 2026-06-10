import type { EventItem } from "./api";

export const DEFAULT_EVENT_WINDOW_DAYS = 30;

export type EventDay = {
  key: string;
  label: string;
  events: EventOccurrence[];
};

export type EventOccurrence = {
  key: string;
  event: EventItem;
  day: Date;
};

const UI_LOCALE = "en-LT";
const dayFormatter = new Intl.DateTimeFormat(UI_LOCALE, {
  weekday: "long",
  month: "long",
  day: "numeric"
});
const dateRangeFormatter = new Intl.DateTimeFormat(UI_LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit"
});

export function todayMorning(): Date {
  const value = new Date();
  value.setHours(0, 0, 0, 0);
  return value;
}

export function addDays(value: Date, days: number): Date {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
}

export function defaultDateTo(dateFrom: Date): Date {
  return addDays(dateFrom, DEFAULT_EVENT_WINDOW_DAYS);
}

export function groupEventsByDay(
  events: EventItem[],
  _windowStart?: Date,
  _windowEnd?: Date
): EventDay[] {
  const grouped = new Map<string, EventOccurrence[]>();
  const rows = events.flatMap((event) => eventOccurrence(event));
  rows.sort(compareOccurrences);
  for (const row of rows) {
    const key = localDateKey(row.day);
    const dayRows = grouped.get(key) ?? [];
    dayRows.push(row);
    grouped.set(key, dayRows);
  }
  return [...grouped.entries()].map(([key, dayRows]) => ({
    key,
    label: dayFormatter.format(dayRows[0].day).toUpperCase(),
    events: dayRows
  }));
}

function eventOccurrence(event: EventItem): EventOccurrence[] {
  const start = new Date(event.starts_at);
  if (Number.isNaN(start.getTime())) {
    return [];
  }
  return [{ key: event.occurrence_id, event, day: startOfLocalDay(start) }];
}

export function formatTimeRange(event: EventItem, occurrenceDay?: Date): string {
  const start = new Date(event.starts_at);
  const startText = start.toLocaleTimeString(UI_LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
  if (!event.ends_at) {
    return startText;
  }
  const end = new Date(event.ends_at);
  if (occurrenceDay && !sameLocalDate(start, end)) {
    return "All day";
  }
  if (!sameLocalDate(start, end)) {
    return `${dateRangeFormatter.format(start)}-${dateRangeFormatter.format(end)}`;
  }
  const endText = end.toLocaleTimeString(UI_LOCALE, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
  return `${startText}-${endText}`;
}

export function formatEventOverflow(event: EventItem): string | null {
  const visibleStart = parseValidDate(event.starts_at);
  if (!visibleStart) {
    return null;
  }
  const originalStart = parseValidDate(event.relevant_from);
  const beforeDays = originalStart ? diffCalendarDays(originalStart, visibleStart) : 0;
  const visibleEnd = parseValidDate(event.ends_at);
  const originalEnd = parseValidDate(event.relevant_to);
  const afterDays = visibleEnd && originalEnd ? diffCalendarDays(visibleEnd, originalEnd) : 0;
  if (beforeDays <= 0 && afterDays <= 0) {
    return null;
  }
  return `-${beforeDays}d | +${afterDays}d`;
}

export function topCategories(event: EventItem, maxItems = 3): string[] {
  return Object.entries(event.category_scores)
    .filter(([, score]) => score > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxItems)
    .map(([category]) => category);
}

function compareOccurrences(a: EventOccurrence, b: EventOccurrence): number {
  return (
    a.day.getTime() - b.day.getTime() ||
    new Date(a.event.starts_at).getTime() - new Date(b.event.starts_at).getTime()
  );
}

function startOfLocalDay(value: Date): Date {
  const day = new Date(value);
  day.setHours(0, 0, 0, 0);
  return day;
}

function localDateKey(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function sameLocalDate(a: Date, b: Date): boolean {
  return localDateKey(a) === localDateKey(b);
}

function parseValidDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function diffCalendarDays(start: Date, end: Date): number {
  const startDay = startOfLocalDay(start);
  const endDay = startOfLocalDay(end);
  return Math.max(0, Math.round((endDay.getTime() - startDay.getTime()) / 86_400_000));
}
