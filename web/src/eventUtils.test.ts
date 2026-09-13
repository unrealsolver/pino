import { describe, expect, it } from "vitest";

import {
  DEFAULT_EVENT_WINDOW_DAYS,
  addDays,
  defaultDateTo,
  eventProgress,
  formatTimeRange,
  groupEventsByDay,
  topCategories
} from "./eventUtils";
import type { EventItem } from "./api";
import { buildVirtualListItems } from "./routes/EventRoute/utils";

// Browser-local fixtures assume Europe/Vilnius; the test script sets TZ before startup.
describe("event utilities", () => {
  it("projects a long interval only into the visible days without copying the event", () => {
    const row = event({
      starts_at: "2025-01-01T00:00:00+02:00",
      ends_at: "2027-01-01T00:00:00+02:00"
    });
    const days = groupEventsByDay([row], new Date(2026, 5, 7), new Date(2026, 5, 10));
    expect(days.map((day) => day.key)).toEqual(["2026-06-07", "2026-06-08", "2026-06-09"]);
    expect(days.every((day) => day.events[0].event === row)).toBe(true);
    const items = buildVirtualListItems(days, new Set(), false);
    expect(new Set(items.map((item) => item.key)).size).toBe(items.length);
    expect(buildVirtualListItems(days, new Set([row.refinement_id]), false)
      .every((item) => item.type === "day")).toBe(true);
  });

  it("keeps recurrence gaps and excludes midnight endings", () => {
    const days = groupEventsByDay([
      event({ occurrence_id: "one", starts_at: "2026-06-07T18:00:00+03:00",
        ends_at: "2026-06-09T00:00:00+03:00" }),
      event({ occurrence_id: "two", starts_at: "2026-06-10T10:00:00+03:00" })
    ], new Date(2026, 5, 7), new Date(2026, 5, 11));
    expect(days.map((day) => day.key)).toEqual(["2026-06-07", "2026-06-08", "2026-06-10"]);
  });

  it("clips point events and rejects invalid intervals", () => {
    const days = groupEventsByDay([
      event({ starts_at: "2026-06-06T10:00:00+03:00" }),
      event({ starts_at: "2026-06-07T00:00:00+03:00" }),
      event({ starts_at: "2026-06-08T00:00:00+03:00" }),
      event({ starts_at: "invalid" }),
      event({ ends_at: "invalid" }),
      event({ ends_at: "2026-06-01T00:00:00+03:00" })
    ], new Date(2026, 5, 7), new Date(2026, 5, 8));
    expect(days).toHaveLength(1);
    expect(days[0].events).toHaveLength(1);
  });

  it.each([
    [new Date(2026, 2, 28), new Date(2026, 2, 31), ["2026-03-28", "2026-03-29", "2026-03-30"]],
    [new Date(2026, 9, 24), new Date(2026, 9, 27), ["2026-10-24", "2026-10-25", "2026-10-26"]]
  ])("uses calendar days across DST changes", (start, end, expected) => {
    const days = groupEventsByDay([event({ starts_at: start.toISOString(), ends_at: end.toISOString() })], start, end);
    expect(days.map((day) => day.key)).toEqual(expected);
  });

  it("labels partial first and last days accurately", () => {
    const row = event({ starts_at: "2026-06-07T18:30:00+03:00", ends_at: "2026-06-09T09:15:00+03:00" });
    expect(formatTimeRange(row, new Date(2026, 5, 7))).toBe("From 18:30");
    expect(formatTimeRange(row, new Date(2026, 5, 8))).toBe("All day");
    expect(formatTimeRange(row, new Date(2026, 5, 9))).toBe("Until 09:15");
  });

  it("groups events by local day and sorts by start time", () => {
    const days = groupEventsByDay([
      event({ refinement_id: "late", starts_at: "2026-06-10T20:00:00+03:00" }),
      event({ refinement_id: "early", starts_at: "2026-06-10T10:00:00+03:00" }),
      event({ refinement_id: "next", starts_at: "2026-06-11T09:00:00+03:00" })
    ]);

    expect(days).toHaveLength(2);
    expect(days[0].events.map((row) => row.event.refinement_id)).toEqual(["early", "late"]);
    expect(days[1].events.map((row) => row.event.refinement_id)).toEqual(["next"]);
  });

  it("uses backend-projected occurrence rows as-is", () => {
    const days = groupEventsByDay(
      [
        event({
          refinement_id: "ongoing",
          occurrence_id: "ongoing:2026-06-07",
          starts_at: "2026-06-06T21:00:00Z",
          ends_at: "2026-06-07T21:00:00Z"
        }),
        event({
          refinement_id: "ongoing",
          occurrence_id: "ongoing:2026-06-08",
          starts_at: "2026-06-07T21:00:00Z",
          ends_at: "2026-06-08T21:00:00Z"
        }),
        event({ refinement_id: "today", starts_at: "2026-06-07T10:00:00+03:00" })
      ],
      new Date("2026-06-07T00:00:00+03:00"),
      new Date("2026-06-09T00:00:00+03:00")
    );

    expect(days[0].key).toBe("2026-06-07");
    expect(days).toHaveLength(2);
    expect(days[0].events.map((row) => row.event.refinement_id)).toEqual(["ongoing", "today"]);
    expect(days[1].events.map((row) => row.event.refinement_id)).toEqual(["ongoing"]);
  });

  it("formats time ranges and top categories", () => {
    const row = event({
      starts_at: "2026-06-10T10:05:00+03:00",
      ends_at: "2026-06-10T12:30:00+03:00",
      category_scores: { workshop: 0.4, electronic_music: 0.9, social: 0.6 }
    });

    expect(formatTimeRange(row)).toContain("10:05");
    expect(formatTimeRange(row)).toContain("12:30");
    expect(topCategories(row, 2)).toEqual(["electronic_music", "social"]);
  });

  it("formats multi-day event ranges as dates", () => {
    const row = event({
      starts_at: "2025-01-01T02:00:00+02:00",
      ends_at: "2027-01-01T01:59:59+02:00"
    });

    expect(formatTimeRange(row)).toContain("2025");
    expect(formatTimeRange(row)).toContain("2027");
  });

  it("formats daily multi-day occurrences as all-day entries", () => {
    const row = event({
      starts_at: "2024-12-31T22:00:00Z",
      ends_at: "2026-12-31T21:59:59Z"
    });

    expect(formatTimeRange(row, new Date("2026-06-07T00:00:00+03:00"))).toBe("All day");
  });

  it("shows progress and days remaining relative to the card day", () => {
    const row = event({
      starts_at: "2026-06-07T21:00:00Z",
      ends_at: "2026-06-27T21:00:00Z",
      relevant_from: "2026-06-02T21:00:00Z",
      relevant_to: "2026-07-17T21:00:00Z"
    });

    expect(eventProgress(row, new Date(2026, 5, 8))?.value).toBe(0);
    expect(eventProgress(row, new Date(2026, 5, 8))?.label).toBe("19 days left");
    expect(eventProgress(row, new Date(2026, 5, 26))?.label).toBe("1 day left");
    expect(eventProgress(row, new Date(2026, 5, 27))?.label).toBe("Ends today");
    expect(eventProgress(row, new Date(2026, 5, 27))?.value).toBe(100);
  });

  it("uses occurrence bounds when original event bounds are missing", () => {
    const row = event({
      starts_at: "2026-06-08T00:00:00+03:00",
      ends_at: "2026-06-28T00:00:00+03:00",
      relevant_from: "",
      relevant_to: null
    });

    expect(eventProgress(row, new Date(2026, 5, 8))?.label).toBe("19 days left");
  });

  it("ignores invalid original event bounds", () => {
    const row = event({
      starts_at: "2026-06-08T00:00:00+03:00",
      ends_at: "2026-06-28T00:00:00+03:00",
      relevant_from: "not-a-date",
      relevant_to: "also-not-a-date"
    });

    expect(eventProgress(row, new Date(2026, 5, 8))?.label).toBe("19 days left");
  });

  it("omits progress for single-day, undated, or invalid intervals", () => {
    const day = new Date(2026, 5, 10);
    expect(eventProgress(event(), day)).toBeNull();
    expect(eventProgress(event({ ends_at: "invalid" }), day)).toBeNull();
    expect(eventProgress(event({ ends_at: "2026-06-11T00:00:00+03:00" }), day)).toBeNull();
  });

  it("counts calendar days across daylight-saving changes", () => {
    const row = event({ starts_at: "2026-03-28T00:00:00+02:00", ends_at: "2026-03-31T00:00:00+03:00" });
    expect(eventProgress(row, new Date(2026, 2, 29))?.value).toBe(50);
    expect(eventProgress(row, new Date(2026, 2, 29))?.label).toBe("1 day left");
  });

  it("adds days without mutating the original date", () => {
    const start = new Date("2026-06-07T00:00:00+03:00");

    expect(addDays(start, 2).toISOString()).toBe("2026-06-08T21:00:00.000Z");
    expect(start.toISOString()).toBe("2026-06-06T21:00:00.000Z");
  });

  it("defaults the event window to 30 days", () => {
    const start = new Date("2026-06-07T00:00:00+03:00");

    expect(DEFAULT_EVENT_WINDOW_DAYS).toBe(30);
    expect(defaultDateTo(start).toISOString()).toBe("2026-07-06T21:00:00.000Z");
  });
});

function event(overrides: Partial<EventItem> = {}): EventItem {
  return {
    refinement_id: "event",
    occurrence_id: "event:2026-06-10T1000",
    title: "Event",
    source: "test",
    url: null,
    summary: null,
    location: null,
    starts_at: "2026-06-10T10:00:00+03:00",
    ends_at: null,
    relevant_from: "2026-06-10T10:00:00+03:00",
    relevant_to: null,
    category_scores: {},
    matching_score: 0,
    ...overrides
  };
}
