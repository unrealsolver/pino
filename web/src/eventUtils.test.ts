import { describe, expect, it } from "vitest";

import {
  DEFAULT_EVENT_WINDOW_DAYS,
  addDays,
  defaultDateTo,
  formatEventOverflow,
  formatTimeRange,
  groupEventsByDay,
  topCategories
} from "./eventUtils";
import type { EventItem } from "./api";

describe("event utilities", () => {
  it("groups events by local day and sorts by start time", () => {
    const days = groupEventsByDay([
      event({ id: "late", starts_at: "2026-06-10T20:00:00+03:00" }),
      event({ id: "early", starts_at: "2026-06-10T10:00:00+03:00" }),
      event({ id: "next", starts_at: "2026-06-11T09:00:00+03:00" })
    ]);

    expect(days).toHaveLength(2);
    expect(days[0].events.map((row) => row.event.id)).toEqual(["early", "late"]);
    expect(days[1].events.map((row) => row.event.id)).toEqual(["next"]);
  });

  it("expands ongoing events across each visible day", () => {
    const days = groupEventsByDay(
      [
        event({
          id: "ongoing",
          starts_at: "2025-01-01T02:00:00+02:00",
          ends_at: "2027-01-01T01:59:59+02:00"
        }),
        event({ id: "today", starts_at: "2026-06-07T10:00:00+03:00" })
      ],
      new Date("2026-06-07T00:00:00+03:00"),
      new Date("2026-06-09T00:00:00+03:00")
    );

    expect(days[0].key).toBe("2026-06-07");
    expect(days).toHaveLength(3);
    expect(days[0].events.map((row) => row.event.id)).toEqual(["ongoing", "today"]);
    expect(days[1].events.map((row) => row.event.id)).toEqual(["ongoing"]);
    expect(days[2].events.map((row) => row.event.id)).toEqual(["ongoing"]);
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
      starts_at: "2025-01-01T02:00:00+02:00",
      ends_at: "2027-01-01T01:59:59+02:00"
    });

    expect(formatTimeRange(row, new Date("2026-06-07T00:00:00+03:00"))).toBe("All day");
  });

  it("formats clipped long-event overflow metadata", () => {
    const row = event({
      starts_at: "2026-06-08T00:00:00+03:00",
      ends_at: "2026-06-28T00:00:00+03:00",
      original_starts_at: "2026-06-03T00:00:00+03:00",
      original_ends_at: "2026-07-18T00:00:00+03:00"
    });

    expect(formatEventOverflow(row)).toBe("-5d | +20d");
  });

  it("does not render NaN when original event bounds are missing", () => {
    const row = event({
      starts_at: "2026-06-08T00:00:00+03:00",
      ends_at: "2026-06-28T00:00:00+03:00",
      original_starts_at: undefined,
      original_ends_at: undefined
    });

    expect(formatEventOverflow(row)).toBeNull();
  });

  it("ignores invalid original event bounds", () => {
    const row = event({
      starts_at: "2026-06-08T00:00:00+03:00",
      ends_at: "2026-06-28T00:00:00+03:00",
      original_starts_at: "not-a-date",
      original_ends_at: "also-not-a-date"
    });

    expect(formatEventOverflow(row)).toBeNull();
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
    id: "event",
    record_id: "record",
    title: "Event",
    source: "test",
    url: null,
    summary: null,
    location: null,
    starts_at: "2026-06-10T10:00:00+03:00",
    ends_at: null,
    original_starts_at: "2026-06-10T10:00:00+03:00",
    original_ends_at: null,
    category_scores: {},
    matching_score: 0,
    ...overrides
  };
}
