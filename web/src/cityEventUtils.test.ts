import { describe, expect, it } from "vitest";

import type { EventItem } from "./api";
import {
  addDays,
  defaultDateTo,
  eventProgress,
  formatTimeRange,
  groupEventsByDay,
  todayMorning
} from "./eventUtils";

const VILNIUS = "Europe/Vilnius";
const NEW_YORK = "America/New_York";

// These tests pass explicit zones and must not depend on the browser timezone.
describe("city-aware event presentation", () => {
  it("groups and labels events by city calendar days", () => {
    const days = groupEventsByDay(
      [
        event({ refinement_id: "late", starts_at: "2026-06-08T03:30:00.000Z" }),
        event({ refinement_id: "morning", starts_at: "2026-06-08T12:00:00.000Z" })
      ],
      new Date("2026-06-07T04:00:00.000Z"),
      new Date("2026-06-09T04:00:00.000Z"),
      NEW_YORK
    );

    expect(days.map((day) => day.key)).toEqual(["2026-06-07", "2026-06-08"]);
    expect(days[0].events[0].event.refinement_id).toBe("late");
    expect(days[0].label).toBe("SUNDAY, 7 JUNE");
    expect(days[1].events[0].event.refinement_id).toBe("morning");
  });

  it("formats the same instant in each explicitly selected city", () => {
    const row = event({ starts_at: "2026-06-08T03:30:00.000Z" });

    expect(formatTimeRange(row, undefined, NEW_YORK)).toBe("23:30");
    expect(formatTimeRange(row, undefined, VILNIUS)).toBe("06:30");
  });

  it("labels partial first and last days in the city zone", () => {
    const row = event({
      starts_at: "2026-06-07T22:30:00.000Z",
      ends_at: "2026-06-09T13:15:00.000Z"
    });

    expect(formatTimeRange(row, new Date("2026-06-07T04:00:00.000Z"), NEW_YORK))
      .toBe("From 18:30");
    expect(formatTimeRange(row, new Date("2026-06-08T04:00:00.000Z"), NEW_YORK))
      .toBe("All day");
    expect(formatTimeRange(row, new Date("2026-06-09T04:00:00.000Z"), NEW_YORK))
      .toBe("Until 09:15");
  });

  it("shows city-local progress labels and ranges across DST", () => {
    const row = event({
      starts_at: "2026-03-07T05:00:00.000Z",
      ends_at: "2026-03-31T04:00:00.000Z"
    });

    const progress = eventProgress(row, new Date("2026-03-15T04:00:00.000Z"), NEW_YORK);
    expect(progress?.label).toBe("15 days left");
    expect(progress?.range).toContain("07/03/2026");
    expect(progress?.range).toContain("30/03/2026");
    expect(progress?.value).toBeCloseTo(8 / 23 * 100);
  });

  it("uses city-local defaults and 30 calendar days across DST", () => {
    const now = new Date("2026-03-07T15:00:00.000Z");
    const from = todayMorning(now, NEW_YORK);
    expect(from.toISOString()).toBe("2026-03-07T05:00:00.000Z");

    expect(defaultDateTo(from, NEW_YORK).toISOString()).toBe("2026-04-06T04:00:00.000Z");
    expect(addDays(from, 1, NEW_YORK).toISOString()).toBe("2026-03-08T05:00:00.000Z");
  });
});

function event(overrides: Partial<EventItem> = {}): EventItem {
  return {
    refinement_id: "event",
    occurrence_id: "event:occurrence",
    title: "Event",
    source: "test",
    url: null,
    location: null,
    starts_at: "2026-06-10T10:00:00.000Z",
    ends_at: null,
    relevant_from: "2026-06-10T10:00:00.000Z",
    relevant_to: null,
    category_scores: {},
    matching_score: 0,
    ...overrides
  };
}
