/**
 * Small, explicit IANA timezone helpers.
 *
 * City browsing never relies on the browser timezone. Instants are converted to
 * wall-clock values in the selected city zone at the UI boundary (pickers,
 * labels, grouping) and back to real instants for URL/filter state.
 *
 * DST wall-time policy:
 * - A wall time that does not exist (spring-forward gap) is rejected for picker
 *   edits. Calendar-day arithmetic advances it by the gap instead.
 * - A wall time that occurs twice (fall-back overlap) resolves to the earlier
 *   instant unless callers preserve an already selected exact instant.
 */

const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;
const partsFormatters = new Map<string, Intl.DateTimeFormat>();
const labelFormatters = new Map<string, Intl.DateTimeFormat>();

export type WallClock = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  millisecond: number;
};

export type PickerValueResult =
  | { instant: Date; error: null }
  | { instant: null; error: "invalid" | "nonexistent" | null };

export function defaultTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

function getPartsFormatter(timeZone: string): Intl.DateTimeFormat {
  const cached = partsFormatters.get(timeZone);
  if (cached) {
    return cached;
  }
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone,
    calendar: "gregory",
    numberingSystem: "latn",
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
  partsFormatters.set(timeZone, formatter);
  return formatter;
}

/** Calendar and clock fields for an instant in an IANA timezone. */
export function getWallClock(instant: Date, timeZone: string): WallClock {
  const values: Record<string, string> = {};
  for (const part of getPartsFormatter(timeZone).formatToParts(instant)) {
    if (part.type !== "literal") {
      values[part.type] = part.value;
    }
  }
  return {
    year: Number(values.year),
    month: Number(values.month),
    day: Number(values.day),
    hour: Number(values.hour),
    minute: Number(values.minute),
    second: Number(values.second),
    millisecond: instant.getUTCMilliseconds()
  };
}

function utcMilliseconds(wall: WallClock): number {
  const date = new Date(0);
  date.setUTCFullYear(wall.year, wall.month - 1, wall.day);
  date.setUTCHours(wall.hour, wall.minute, wall.second, wall.millisecond);
  return date.getTime();
}

function offsetMillisecondsAt(instantMs: number, timeZone: string): number {
  const secondStart = instantMs - (((instantMs % 1000) + 1000) % 1000);
  const wall = getWallClock(new Date(secondStart), timeZone);
  return utcMilliseconds({ ...wall, millisecond: 0 }) - secondStart;
}

function sameWallClock(a: WallClock, b: WallClock): boolean {
  return (
    a.year === b.year &&
    a.month === b.month &&
    a.day === b.day &&
    a.hour === b.hour &&
    a.minute === b.minute &&
    a.second === b.second &&
    a.millisecond === b.millisecond
  );
}

/**
 * All real instants that display the given wall time in the timezone. Usually
 * one, zero for a spring-forward gap, two for a fall-back overlap.
 *
 * Offsets are sampled on both sides of the wall time, not just at the target
 * interpreted as UTC. A DST transition can otherwise hide the earlier overlap
 * occurrence (for example Vilnius 2026-10-25 03:30).
 */
export function wallClockCandidates(wall: WallClock, timeZone: string): Date[] {
  const target = utcMilliseconds(wall);
  const offsets = new Set<number>();
  for (const dayOffset of [-2, -1, 0, 1, 2]) {
    offsets.add(offsetMillisecondsAt(target + dayOffset * MILLISECONDS_PER_DAY, timeZone));
  }
  const candidates = [...offsets]
    .map((offset) => target - offset)
    .filter((value, index, all) => all.indexOf(value) === index)
    .filter((value) => sameWallClock(getWallClock(new Date(value), timeZone), wall));
  return candidates.sort((a, b) => a - b).map((value) => new Date(value));
}

/** Resolve a wall time, choosing the earlier instant for overlaps. */
export function wallClockToInstant(wall: WallClock, timeZone: string): Date | null {
  return wallClockCandidates(wall, timeZone)[0] ?? null;
}

/** Resolve a wall time, advancing by the DST gap when the time is nonexistent. */
export function wallClockToInstantAdvancingGap(wall: WallClock, timeZone: string): Date {
  const candidate = wallClockToInstant(wall, timeZone);
  if (candidate) {
    return candidate;
  }
  const target = utcMilliseconds(wall);
  // The offset before the transition maps the target clock forward by the gap.
  const offsetBefore = offsetMillisecondsAt(target - MILLISECONDS_PER_DAY, timeZone);
  return new Date(target - offsetBefore);
}

export function startOfDayInTimeZone(instant: Date, timeZone: string): Date {
  const wall = getWallClock(instant, timeZone);
  return wallClockToInstantAdvancingGap(
    { ...wall, hour: 0, minute: 0, second: 0, millisecond: 0 },
    timeZone
  );
}

export function todayMidnightInTimeZone(now: Date, timeZone: string): Date {
  return startOfDayInTimeZone(now, timeZone);
}

/**
 * Add calendar days while preserving the city-local clock time. The offset is
 * re-evaluated for the target date; a nonexistent target advances by the gap.
 */
export function addCalendarDaysInTimeZone(
  instant: Date,
  days: number,
  timeZone: string
): Date {
  const wall = getWallClock(instant, timeZone);
  const calendar = new Date(0);
  calendar.setUTCFullYear(wall.year, wall.month - 1, wall.day + days);
  const target: WallClock = {
    ...wall,
    year: calendar.getUTCFullYear(),
    month: calendar.getUTCMonth() + 1,
    day: calendar.getUTCDate()
  };
  return wallClockToInstantAdvancingGap(target, timeZone);
}

/** YYYY-MM-DD key for an instant in the city timezone. */
export function dateKeyInTimeZone(instant: Date, timeZone: string): string {
  const wall = getWallClock(instant, timeZone);
  return `${String(wall.year).padStart(4, "0")}-${String(wall.month).padStart(2, "0")}-${String(
    wall.day
  ).padStart(2, "0")}`;
}

/** Calendar-day difference based on city-local dates, not elapsed hours. */
export function diffCalendarDaysInTimeZone(start: Date, end: Date, timeZone: string): number {
  const startWall = getWallClock(start, timeZone);
  const endWall = getWallClock(end, timeZone);
  const startDay = utcMilliseconds({ ...startWall, hour: 0, minute: 0, second: 0, millisecond: 0 });
  const endDay = utcMilliseconds({ ...endWall, hour: 0, minute: 0, second: 0, millisecond: 0 });
  return Math.round((endDay - startDay) / MILLISECONDS_PER_DAY);
}

/** Picker boundary: real instant -> city wall-clock string. */
export function formatPickerValue(instant: Date, timeZone: string): string {
  const wall = getWallClock(instant, timeZone);
  return (
    `${String(wall.year).padStart(4, "0")}-${String(wall.month).padStart(2, "0")}-` +
    `${String(wall.day).padStart(2, "0")} ${String(wall.hour).padStart(2, "0")}:` +
    `${String(wall.minute).padStart(2, "0")}:${String(wall.second).padStart(2, "0")}`
  );
}

const WALL_STRING_PATTERN =
  /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/;

function parseWallString(value: string): WallClock | null {
  const match = WALL_STRING_PATTERN.exec(value);
  if (!match) {
    return null;
  }
  const wall: WallClock = {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4]),
    minute: Number(match[5]),
    second: match[6] ? Number(match[6]) : 0,
    millisecond: 0
  };
  const normalized = new Date(utcMilliseconds(wall));
  return normalized.getUTCFullYear() === wall.year &&
    normalized.getUTCMonth() === wall.month - 1 &&
    normalized.getUTCDate() === wall.day &&
    normalized.getUTCHours() === wall.hour &&
    normalized.getUTCMinutes() === wall.minute &&
    normalized.getUTCSeconds() === wall.second
    ? wall
    : null;
}

function sameDisplayedWallTime(a: WallClock, b: WallClock): boolean {
  return (
    a.year === b.year &&
    a.month === b.month &&
    a.day === b.day &&
    a.hour === b.hour &&
    a.minute === b.minute
  );
}

/**
 * Picker boundary: city wall-clock string -> real instant.
 *
 * The picker works with wall-clock strings, so a browser-local `new Date(string)`
 * is never used. Re-emitting the currently displayed wall time preserves the
 * exact selected instant, which keeps a URL-selected later overlap occurrence.
 */
export function pickerValueToInstant(
  value: Date | string | null | undefined,
  currentInstant: Date | null,
  timeZone: string
): PickerValueResult {
  if (value === null || value === undefined || value === "") {
    return { instant: null, error: null };
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime())
      ? { instant: null, error: "invalid" }
      : { instant: value, error: null };
  }

  const wall = parseWallString(value);
  if (!wall) {
    return { instant: null, error: "invalid" };
  }
  if (
    currentInstant &&
    sameDisplayedWallTime(getWallClock(currentInstant, timeZone), wall)
  ) {
    return { instant: currentInstant, error: null };
  }
  const instant = wallClockToInstant(wall, timeZone);
  return instant ? { instant, error: null } : { instant: null, error: "nonexistent" };
}

/** Cached Intl formatter for city-local labels. */
export function formatInTimeZone(
  instant: Date,
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
  locale = "en-LT"
): string {
  const key = `${locale}|${timeZone}|${JSON.stringify(options)}`;
  let formatter = labelFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(locale, { ...options, timeZone });
    labelFormatters.set(key, formatter);
  }
  return formatter.format(instant);
}
