import { afterEach, describe, expect, it, vi } from "vitest";

import { eventQueryKey, fetchEvents, serializeEventFilters, type EventFilters } from "./api";

describe("events API", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("builds stable TanStack Query keys from filters", () => {
    const filters = eventFilters();

    expect(eventQueryKey(filters)).toEqual([
      "events",
      {
        categories: ["social"],
        minScore: 0.5,
        query: "jam",
        dateFrom: "2026-06-08T07:00:00.000Z",
        dateTo: null
      }
    ]);
  });

  it("serializes event filters for query keys and requests", () => {
    expect(serializeEventFilters(eventFilters())).toEqual({
      categories: ["social"],
      minScore: 0.5,
      query: "jam",
      dateFrom: "2026-06-08T07:00:00.000Z",
      dateTo: null
    });
  });

  it("forwards abort signals to fetch", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ timezone: "Europe/Vilnius", categories: [], events: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchEvents(eventFilters(), { signal: controller.signal });

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ signal: controller.signal });
  });
});

function eventFilters(): EventFilters {
  return {
    categories: ["social"],
    minScore: 0.5,
    query: "jam",
    dateFrom: new Date("2026-06-08T10:00:00+03:00"),
    dateTo: null
  };
}
