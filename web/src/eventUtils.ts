import type { EventItem } from "./api";
import {
  addCalendarDaysInTimeZone,
  dateKeyInTimeZone,
  defaultTimeZone,
  diffCalendarDaysInTimeZone,
  formatInTimeZone,
  startOfDayInTimeZone,
  todayMidnightInTimeZone
} from "./timezone";

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

/** City-local midnight for "today"; legacy callers may omit the timezone. */
export function todayMorning(
  reference: Date = new Date(),
  timeZone: string = defaultTimeZone()
): Date {
  return todayMidnightInTimeZone(reference, timeZone);
}

/** Adds calendar days while preserving the city-local clock time across DST. */
export function addDays(
  value: Date,
  days: number,
  timeZone: string = defaultTimeZone()
): Date {
  return addCalendarDaysInTimeZone(value, days, timeZone);
}

export function defaultDateTo(
  dateFrom: Date,
  timeZone: string = defaultTimeZone()
): Date {
  return addDays(dateFrom, DEFAULT_EVENT_WINDOW_DAYS, timeZone);
}

export function groupEventsByDay(
  events: EventItem[],
  windowStart?: Date,
  windowEnd?: Date,
  timeZone: string = defaultTimeZone()
): EventDay[] {
  const grouped = new Map<string, EventOccurrence[]>();
  const rows = events.flatMap((event) =>
    eventOccurrences(event, timeZone, windowStart, windowEnd)
  );
  rows.sort(compareOccurrences);
  for (const row of rows) {
    const key = dateKeyInTimeZone(row.day, timeZone);
    const dayRows = grouped.get(key) ?? [];
    dayRows.push(row);
    grouped.set(key, dayRows);
  }
  return [...grouped.entries()].map(([key, dayRows]) => ({
    key,
    label: formatInTimeZone(
      dayRows[0].day,
      timeZone,
      { weekday: "long", month: "long", day: "numeric" },
      UI_LOCALE
    ).toUpperCase(),
    events: dayRows
  }));
}

function eventOccurrences(
  event: EventItem,
  timeZone: string,
  windowStart?: Date,
  windowEnd?: Date
): EventOccurrence[] {
  const start = parseValidDate(event.starts_at);
  const end = parseValidDate(event.ends_at);
  if (!start || (event.ends_at && (!end || end < start))) {
    return [];
  }
  const from = Math.max(start.getTime(), windowStart?.getTime() ?? -Infinity);
  const to = Math.min(end?.getTime() ?? start.getTime(), windowEnd?.getTime() ?? Infinity);
  // Missing/zero duration is a point event; interval endings are exclusive.
  const isPoint = !end || end.getTime() === start.getTime();
  if (isPoint) {
    if (start.getTime() < from || start.getTime() >= (windowEnd?.getTime() ?? Infinity)) {
      return [];
    }
    const day = startOfDayInTimeZone(start, timeZone);
    return [
      {
        key: `${event.occurrence_id}:${dateKeyInTimeZone(day, timeZone)}`,
        event,
        day
      }
    ];
  }
  if (to <= from) {
    return [];
  }
  const rows: EventOccurrence[] = [];
  let day = startOfDayInTimeZone(new Date(from), timeZone);
  while (day.getTime() < to) {
    rows.push({
      key: `${event.occurrence_id}:${dateKeyInTimeZone(day, timeZone)}`,
      event,
      day
    });
    day = addDays(day, 1, timeZone);
  }
  return rows;
}

export function formatTimeRange(
  event: EventItem,
  occurrenceDay?: Date,
  timeZone: string = defaultTimeZone()
): string {
  const start = new Date(event.starts_at);
  const startText = formatInTimeZone(
    start,
    timeZone,
    { hour: "2-digit", minute: "2-digit", hour12: false },
    UI_LOCALE
  );
  if (!event.ends_at) {
    return startText;
  }
  const end = new Date(event.ends_at);
  if (occurrenceDay && !sameLocalDate(start, end, timeZone)) {
    const dayStart = startOfDayInTimeZone(occurrenceDay, timeZone);
    const dayEnd = addDays(dayStart, 1, timeZone);
    if (start <= dayStart && end >= dayEnd) {
      return "All day";
    }
    if (start > dayStart) {
      return `From ${startText}`;
    }
    return `Until ${formatInTimeZone(
      end,
      timeZone,
      { hour: "2-digit", minute: "2-digit", hour12: false },
      UI_LOCALE
    )}`;
  }
  if (!sameLocalDate(start, end, timeZone)) {
    return `${formatDateRange(start, timeZone)}-${formatDateRange(end, timeZone)}`;
  }
  const endText = formatInTimeZone(
    end,
    timeZone,
    { hour: "2-digit", minute: "2-digit", hour12: false },
    UI_LOCALE
  );
  return `${startText}-${endText}`;
}

export function eventProgress(
  event: EventItem,
  day: Date,
  timeZone: string = defaultTimeZone()
) {
  const start = parseValidDate(event.starts_at);
  const end = parseValidDate(event.ends_at);
  if (!start || !end || end <= start || Number.isNaN(day.getTime())) {
    return null;
  }
  // Midnight belongs to the preceding event day, consistent with calendar grouping.
  const lastDay = new Date(end.getTime() - 1);
  const span = diffCalendarDaysInTimeZone(start, lastDay, timeZone);
  if (span === 0) {
    return null;
  }
  const elapsed = Math.min(
    span,
    diffCalendarDaysInTimeZone(start, day, timeZone)
  );
  const remaining = span - elapsed;
  return {
    value: elapsed / span * 100,
    label: remaining === 0 ? "Ends today" : `${remaining} ${remaining === 1 ? "day" : "days"} left`,
    range: `${formatDateRange(start, timeZone)} – ${formatDateRange(lastDay, timeZone)}`
  };
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

function sameLocalDate(a: Date, b: Date, timeZone: string): boolean {
  return dateKeyInTimeZone(a, timeZone) === dateKeyInTimeZone(b, timeZone);
}

function formatDateRange(value: Date, timeZone: string): string {
  return formatInTimeZone(
    value,
    timeZone,
    { year: "numeric", month: "2-digit", day: "2-digit" },
    UI_LOCALE
  );
}

function parseValidDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}
