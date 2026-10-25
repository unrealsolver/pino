import { describe, expect, it } from "vitest";

import {
  addCalendarDaysInTimeZone,
  dateKeyInTimeZone,
  diffCalendarDaysInTimeZone,
  formatPickerValue,
  getWallClock,
  pickerValueToInstant,
  startOfDayInTimeZone,
  todayMidnightInTimeZone,
  wallClockCandidates,
  wallClockToInstant,
  wallClockToInstantAdvancingGap,
  type WallClock
} from "./timezone";

const VILNIUS = "Europe/Vilnius";
const NEW_YORK = "America/New_York";

function wall(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  second = 0
): WallClock {
  return { year, month, day, hour, minute, second, millisecond: 0 };
}

describe("city wall-clock conversion", () => {
  it("formats instants in the selected city zone rather than the browser zone", () => {
    const instant = new Date("2026-06-08T21:30:00.000Z");

    expect(formatPickerValue(instant, VILNIUS)).toBe("2026-06-09 00:30:00");
    expect(formatPickerValue(instant, NEW_YORK)).toBe("2026-06-08 17:30:00");
    expect(getWallClock(instant, VILNIUS)).toMatchObject({
      year: 2026,
      month: 6,
      day: 9,
      hour: 0,
      minute: 30
    });
  });

  it("uses city-local midnight for today around a foreign midnight", () => {
    const now = new Date("2026-06-08T21:30:00.000Z");

    expect(todayMidnightInTimeZone(now, VILNIUS).toISOString())
      .toBe("2026-06-08T21:00:00.000Z");
    expect(todayMidnightInTimeZone(now, NEW_YORK).toISOString())
      .toBe("2026-06-08T04:00:00.000Z");
  });

  it("finds both fall-back overlap occurrences and chooses the earlier one", () => {
    // Vilnius 2026-10-25 03:30 occurs at 00:30Z (EEST) and 01:30Z (EET).
    const candidates = wallClockCandidates(wall(2026, 10, 25, 3, 30), VILNIUS);
    expect(candidates.map((value) => value.toISOString())).toEqual([
      "2026-10-25T00:30:00.000Z",
      "2026-10-25T01:30:00.000Z"
    ]);
    expect(wallClockToInstant(wall(2026, 10, 25, 3, 30), VILNIUS)?.toISOString())
      .toBe("2026-10-25T00:30:00.000Z");
    expect(
      pickerValueToInstant("2026-10-25 03:30:00", null, VILNIUS)
    ).toEqual({
      instant: new Date("2026-10-25T00:30:00.000Z"),
      error: null
    });

    const later = new Date("2026-10-25T01:30:00.000Z");
    expect(
      pickerValueToInstant("2026-10-25 03:30:00", later, VILNIUS)
    ).toEqual({ instant: later, error: null });
  });

  it("finds New York fall-back overlaps and resolves ambiguous edits earlier", () => {
    const candidates = wallClockCandidates(wall(2026, 11, 1, 1, 30), NEW_YORK);
    expect(candidates.map((value) => value.toISOString())).toEqual([
      "2026-11-01T05:30:00.000Z",
      "2026-11-01T06:30:00.000Z"
    ]);

    expect(
      pickerValueToInstant("2026-11-01 01:30:00", null, NEW_YORK)
    ).toEqual({
      instant: new Date("2026-11-01T05:30:00.000Z"),
      error: null
    });
  });

  it("preserves an explicit later overlap instant when the picker re-emits it", () => {
    const later = new Date("2026-11-01T06:30:00.000Z");

    expect(
      pickerValueToInstant("2026-11-01 01:30:00", later, NEW_YORK)
    ).toEqual({ instant: later, error: null });
    // A different displayed wall time is a new entry and uses the earlier occurrence.
    expect(
      pickerValueToInstant("2026-11-01 01:31:00", later, NEW_YORK)
    ).toEqual({
      instant: new Date("2026-11-01T05:31:00.000Z"),
      error: null
    });
  });

  it("rejects nonexistent picker wall times but advances calendar arithmetic", () => {
    expect(wallClockToInstant(wall(2026, 3, 8, 2, 30), NEW_YORK)).toBeNull();
    expect(
      pickerValueToInstant("2026-03-08 02:30:00", null, NEW_YORK)
    ).toEqual({ instant: null, error: "nonexistent" });
    expect(
      wallClockToInstantAdvancingGap(wall(2026, 3, 8, 2, 30), NEW_YORK).toISOString()
    ).toBe("2026-03-08T07:30:00.000Z");
  });

  it("re-evaluates the offset after calendar-day changes across DST", () => {
    const spring = new Date("2026-03-01T05:00:00.000Z");
    expect(addCalendarDaysInTimeZone(spring, 30, NEW_YORK).toISOString())
      .toBe("2026-03-31T04:00:00.000Z");

    const fall = new Date("2026-10-10T04:00:00.000Z");
    expect(addCalendarDaysInTimeZone(fall, 30, NEW_YORK).toISOString())
      .toBe("2026-11-09T05:00:00.000Z");
  });

  it("advances a calendar target by the gap when its clock time is nonexistent", () => {
    const start = new Date("2026-03-07T07:30:00.000Z");
    expect(formatPickerValue(start, NEW_YORK)).toBe("2026-03-07 02:30:00");

    const next = addCalendarDaysInTimeZone(start, 1, NEW_YORK);
    expect(next.toISOString()).toBe("2026-03-08T07:30:00.000Z");
    expect(formatPickerValue(next, NEW_YORK)).toBe("2026-03-08 03:30:00");
  });

  it("groups dates and differences by city calendar days across DST", () => {
    const start = new Date("2026-03-07T05:00:00.000Z");
    const end = new Date("2026-03-11T04:00:00.000Z");

    expect(dateKeyInTimeZone(start, NEW_YORK)).toBe("2026-03-07");
    expect(dateKeyInTimeZone(end, NEW_YORK)).toBe("2026-03-11");
    expect(diffCalendarDaysInTimeZone(start, end, NEW_YORK)).toBe(4);
    expect(startOfDayInTimeZone(new Date("2026-03-08T15:00:00.000Z"), NEW_YORK).toISOString())
      .toBe("2026-03-08T05:00:00.000Z");
  });

  it("round-trips supported extreme-year instants without browser-local parsing", () => {
    for (const iso of ["0002-01-01T05:00:00.000Z", "9998-12-01T00:00:00.000Z"]) {
      const instant = new Date(iso);
      const wallValue = formatPickerValue(instant, VILNIUS);
      const roundTrip = pickerValueToInstant(wallValue, null, VILNIUS);
      expect(roundTrip.error).toBeNull();
      expect(roundTrip.instant?.toISOString()).toBe(iso);
    }
  });
});
