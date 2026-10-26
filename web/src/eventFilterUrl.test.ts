import { describe, expect, it } from "vitest";

import type { EventFilters } from "./api";
import {
  MAX_EVENT_FILTER_CATEGORIES,
  MAX_EVENT_FILTER_QUERY_LENGTH,
  eventFilterParamsNeedNormalization,
  eventFiltersEqual,
  eventFiltersToSearchParams,
  hasEventFilterParams,
  normalizeEventFilters,
  parseEventFilterParams,
  removeEventFilterParams
} from "./eventFilterUrl";

// Fixed browser-local "now" (Europe/Vilnius, as the test command pins the timezone).
const NOW = new Date("2026-06-08T00:30:00+03:00");
const DEFAULT_DATE_FROM = "2026-06-07T21:00:00.000Z";
const DEFAULT_DATE_TO = "2026-07-07T21:00:00.000Z";

describe("event filter URL parsing", () => {
  it("falls back to the browser-local default window with no parameters", () => {
    expect(parseEventFilterParams(new URLSearchParams(), NOW)).toEqual({
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: new Date(DEFAULT_DATE_FROM),
      dateTo: new Date(DEFAULT_DATE_TO)
    });
  });

  it("parses and normalizes a fully specified query", () => {
    const filters = parseEventFilterParams(
      params({
        date_from: "2026-06-08T10:00:00+03:00",
        date_to: "2026-07-08T10:00:00+03:00",
        category: [" social ", "music", "social", "  "],
        min_score: "0.4",
        q: "jam session"
      }),
      NOW
    );

    expect(filters).toEqual({
      categories: ["music", "social"],
      minScore: 0.4,
      query: "jam session",
      dateFrom: new Date("2026-06-08T07:00:00.000Z"),
      dateTo: new Date("2026-07-08T07:00:00.000Z")
    });
  });

  it.each([
    ["timezone-less", "2026-06-08T10:00"],
    ["impossible calendar day", "2026-02-30T00:00:00Z"],
    ["unparseable", "not-a-date"]
  ])("rejects a %s date_from and uses the local default", (_label, value) => {
    const filters = parseEventFilterParams(params({ date_from: value }), NOW);
    expect(filters.dateFrom).toEqual(new Date(DEFAULT_DATE_FROM));
    expect(filters.dateTo).toEqual(new Date(DEFAULT_DATE_TO));
  });

  it("accepts a valid leap day and an explicit numeric offset", () => {
    const leap = parseEventFilterParams(
      params({ date_from: "2024-02-29T00:00:00Z", date_to: "2024-03-30T00:00:00Z" }),
      NOW
    );
    expect(leap.dateFrom).toEqual(new Date("2024-02-29T00:00:00.000Z"));

    const offset = parseEventFilterParams(
      params({ date_from: "2026-06-08T10:00:00-05:00" }),
      NOW
    );
    expect(offset.dateFrom).toEqual(new Date("2026-06-08T15:00:00.000Z"));
  });

  it("resets the end when it precedes the start", () => {
    const filters = parseEventFilterParams(
      params({ date_from: "2026-06-08T00:00:00Z", date_to: "2026-06-01T00:00:00Z" }),
      NOW
    );
    expect(filters.dateTo).toEqual(new Date("2026-07-08T00:00:00.000Z"));
  });

  it("keeps exactly 370 days and resets anything longer", () => {
    const allowed = parseEventFilterParams(
      params({ date_from: "2026-01-01T00:00:00Z", date_to: "2027-01-06T00:00:00Z" }),
      NOW
    );
    expect(allowed.dateTo).toEqual(new Date("2027-01-06T00:00:00.000Z"));

    const tooLong = parseEventFilterParams(
      params({ date_from: "2026-01-01T00:00:00Z", date_to: "2027-01-07T00:00:00Z" }),
      NOW
    );
    expect(tooLong.dateTo).toEqual(new Date("2026-01-31T00:00:00.000Z"));
  });

  it("rejects boundary years the API refuses", () => {
    for (const value of ["9999-12-31T00:00:00Z", "0001-01-01T00:00:00Z"]) {
      expect(parseEventFilterParams(params({ date_from: value }), NOW).dateFrom).toEqual(
        new Date(DEFAULT_DATE_FROM)
      );
    }
  });

  it("validates supported years after UTC conversion", () => {
    // Raw string year is 9998/0002 but the UTC instant falls outside 2..9998.
    for (const value of ["9998-12-31T23:30:00-05:00", "0002-01-01T02:00:00+05:00"]) {
      const filters = parseEventFilterParams(params({ date_from: value }), NOW);
      expect(filters.dateFrom).toEqual(new Date(DEFAULT_DATE_FROM));
      expect(filters.dateTo).toEqual(new Date(DEFAULT_DATE_TO));
    }

    const supported = parseEventFilterParams(
      params({ date_from: "0002-01-01T05:00:00Z" }),
      NOW
    );
    expect(supported.dateFrom).toEqual(new Date("0002-01-01T05:00:00.000Z"));
  });

  it("keeps a late-9998 start that can still produce a valid default end", () => {
    const filters = parseEventFilterParams(
      params({ date_from: "9998-12-01T00:00:00Z" }),
      NOW
    );
    expect(filters.dateFrom).toEqual(new Date("9998-12-01T00:00:00.000Z"));
    expect(filters.dateTo).toEqual(new Date("9998-12-31T00:00:00.000Z"));
  });

  it("falls back to the current default window when a start cannot produce a valid default end", () => {
    for (const value of ["9998-12-30T00:00:00Z", "9998-12-31T00:00:00Z"]) {
      const filters = parseEventFilterParams(
        params({ date_from: value, date_to: "9998-12-31T00:00:00Z" }),
        NOW
      );
      expect(filters.dateFrom).toEqual(new Date(DEFAULT_DATE_FROM));
      expect(filters.dateTo).toEqual(new Date(DEFAULT_DATE_TO));
      expect(filters.dateTo?.getUTCFullYear()).not.toBe(9999);
    }
  });

  it("uses both current defaults when a rejected start has a valid unrelated end", () => {
    const filters = parseEventFilterParams(
      params({
        date_from: "9998-12-30T00:00:00Z",
        date_to: "2026-06-25T00:00:00Z"
      }),
      NOW
    );
    expect(filters.dateFrom).toEqual(new Date(DEFAULT_DATE_FROM));
    expect(filters.dateTo).toEqual(new Date(DEFAULT_DATE_TO));
  });

  it.each([
    ["nan", 0],
    ["1.5", 0],
    ["-0.1", 0],
    ["abc", 0],
    ["", 0],
    ["0", 0],
    ["0.75", 0.75],
    ["1", 1]
  ])("clamps min_score %j to %j", (value, expected) => {
    expect(parseEventFilterParams(params({ min_score: value }), NOW).minScore).toBe(expected);
  });

  it("trims, de-duplicates, then sorts categories without dropping unknown names", () => {
    const filters = parseEventFilterParams(
      params({ category: ["zeta", " alpha ", "alpha", "zeta", "unknown_kind", "beta"] }),
      NOW
    );
    // " alpha " and "alpha" collapse only because trimming happens before de-duplication.
    expect(filters.categories).toEqual(["alpha", "beta", "unknown_kind", "zeta"]);
  });

  it("caps categories at 64 after the de-duplicated set is sorted", () => {
    const entries = Array.from(
      { length: MAX_EVENT_FILTER_CATEGORIES + 6 },
      (_value, index) => `c${String(index).padStart(2, "0")}`
    );
    // Duplicates must not consume cap slots.
    const filters = parseEventFilterParams(params({ category: [...entries, ...entries] }), NOW);

    expect(filters.categories).toHaveLength(MAX_EVENT_FILTER_CATEGORIES);
    expect(filters.categories[0]).toBe("c00");
    expect(filters.categories.at(-1)).toBe("c63");
  });

  it("preserves query text including spaces while capping its length", () => {
    expect(parseEventFilterParams(params({ q: "  two words  " }), NOW).query).toBe("  two words  ");
    const long = "x".repeat(MAX_EVENT_FILTER_QUERY_LENGTH + 20);
    expect(parseEventFilterParams(params({ q: long }), NOW).query).toHaveLength(
      MAX_EVENT_FILTER_QUERY_LENGTH
    );
  });

  it("uses the first value for repeated scalar keys", () => {
    const filters = parseEventFilterParams(
      params({ min_score: ["0.9", "0.1"], q: ["first", "second"], date_from: ["2026-06-08T00:00:00Z", "2026-01-01T00:00:00Z"] }),
      NOW
    );
    expect(filters.minScore).toBe(0.9);
    expect(filters.query).toBe("first");
    expect(filters.dateFrom).toEqual(new Date("2026-06-08T00:00:00.000Z"));
  });
});

describe("city-local date-only filter bounds", () => {
  const VILNIUS = "Europe/Vilnius";
  const NEW_YORK = "America/New_York";
  const DEFAULT_WINDOW = {
    dateFrom: new Date(DEFAULT_DATE_FROM),
    dateTo: new Date(DEFAULT_DATE_TO)
  };

  it("resolves date-only From and exclusive To to city-local midnight", () => {
    const filters = parseEventFilterParams(
      params({ date_from: "2026-06-08", date_to: "2026-07-08" }),
      NOW,
      VILNIUS
    );

    expect(filters.dateFrom).toEqual(new Date("2026-06-07T21:00:00.000Z"));
    expect(filters.dateTo).toEqual(new Date("2026-07-07T21:00:00.000Z"));
  });

  it("spans 25 elapsed hours for the Vilnius 2026-10-25 DST day", () => {
    const filters = parseEventFilterParams(
      params({ date_from: "2026-10-25", date_to: "2026-10-26" }),
      NOW,
      VILNIUS
    );

    expect(filters.dateFrom).toEqual(new Date("2026-10-24T21:00:00.000Z"));
    expect(filters.dateTo).toEqual(new Date("2026-10-25T22:00:00.000Z"));
    expect(filters.dateTo?.getTime()).toBe(
      filters.dateFrom.getTime() + 25 * 60 * 60 * 1000
    );
  });

  it("resolves the same state for date-only and equivalent explicit instants", () => {
    const dateOnly = parseEventFilterParams(
      params({ date_from: "2026-10-25", date_to: "2026-10-26" }),
      NOW,
      VILNIUS
    );
    const explicit = parseEventFilterParams(
      params({
        date_from: "2026-10-24T21:00:00.000Z",
        date_to: "2026-10-25T22:00:00.000Z"
      }),
      NOW,
      VILNIUS
    );

    expect(eventFiltersEqual(dateOnly, explicit)).toBe(true);
  });

  it.each([
    ["month 13", "2026-13-01"],
    ["month 00", "2026-00-10"],
    ["day 00", "2026-01-00"],
    ["day 32", "2026-01-32"],
    ["April 31", "2026-04-31"],
    ["rolled February 30", "2026-02-30"],
    ["non-leap February 29", "2025-02-29"],
    ["century non-leap February 29", "2100-02-29"],
    ["single-digit month", "2026-6-01"],
    ["single-digit day", "2026-06-1"],
    ["short year", "26-06-01"],
    ["trailing newline", "2026-01-01\n"],
    ["year 0000", "0000-01-01"],
    ["year 0001", "0001-01-01"],
    ["year 9999", "9999-01-01"]
  ])("rejects %s date-only bounds with the ordinary fallback", (_label, value) => {
    const filters = parseEventFilterParams(params({ date_from: value }), NOW, VILNIUS);
    expect(filters.dateFrom).toEqual(DEFAULT_WINDOW.dateFrom);
    expect(filters.dateTo).toEqual(DEFAULT_WINDOW.dateTo);
  });

  it("accepts real leap days including the 2000 century exception", () => {
    for (const value of ["2024-02-29", "2000-02-29"]) {
      const filters = parseEventFilterParams(params({ date_from: value }), NOW, VILNIUS);
      expect(filters.dateFrom).toEqual(new Date(`${value}T00:00:00+02:00`));
    }
  });

  it("rejects invalid bounds independently while keeping a valid From", () => {
    const filters = parseEventFilterParams(
      params({ date_from: "2026-06-08", date_to: "2026-02-30" }),
      NOW,
      VILNIUS
    );

    expect(filters.dateFrom).toEqual(new Date("2026-06-07T21:00:00.000Z"));
    expect(filters.dateTo).toEqual(new Date("2026-07-07T21:00:00.000Z"));
  });

  it("validates supported years on the resolved UTC instant", () => {
    // Vilnius local midnight on 0002-01-01 resolves to year 0001 in UTC.
    const pushedOut = parseEventFilterParams(
      params({ date_from: "0002-01-01" }),
      NOW,
      VILNIUS
    );
    expect(pushedOut.dateFrom).toEqual(DEFAULT_WINDOW.dateFrom);
    expect(pushedOut.dateTo).toEqual(DEFAULT_WINDOW.dateTo);

    const inside = parseEventFilterParams(params({ date_from: "0002-01-02" }), NOW, VILNIUS);
    expect(inside.dateFrom).toEqual(new Date("0002-01-01T22:18:44.000Z"));

    const upper = parseEventFilterParams(params({ date_from: "9998-12-01" }), NOW, VILNIUS);
    expect(upper.dateFrom).toEqual(new Date("9998-11-30T22:00:00.000Z"));
    expect(upper.dateTo?.getUTCFullYear()).toBe(9998);
  });

  it("rejects a date whose local midnight does not exist instead of shifting it", () => {
    const fallback = parseEventFilterParams(new URLSearchParams(), NOW, "America/Santiago");
    const filters = parseEventFilterParams(
      params({ date_from: "2026-09-06", date_to: "2026-09-06" }),
      NOW,
      "America/Santiago"
    );

    expect(filters).toEqual(fallback);
  });

  it("preserves explicit-zone second and millisecond precision, including the later fold", () => {
    const precise = parseEventFilterParams(
      params({ date_from: "2026-11-01T01:30:00.123-05:00" }),
      NOW,
      NEW_YORK
    );
    expect(precise.dateFrom).toEqual(new Date("2026-11-01T06:30:00.123Z"));

    const earlier = parseEventFilterParams(
      params({ date_from: "2026-11-01T01:30:00-04:00" }),
      NOW,
      NEW_YORK
    );
    const later = parseEventFilterParams(
      params({ date_from: "2026-11-01T01:30:00-05:00" }),
      NOW,
      NEW_YORK
    );
    expect(earlier.dateFrom).toEqual(new Date("2026-11-01T05:30:00.000Z"));
    expect(later.dateFrom).toEqual(new Date("2026-11-01T06:30:00.000Z"));

    const truncated = parseEventFilterParams(
      params({ date_from: "2026-06-08T10:00:00.987654321+03:00" }),
      NOW,
      VILNIUS
    );
    expect(truncated.dateFrom).toEqual(new Date("2026-06-08T07:00:00.987Z"));
  });

  it.each([
    ["timezone-less", "2026-11-01T01:30:00"],
    ["timezone-less with fraction", "2026-11-01T01:30:00.123"]
  ])("keeps %s full timestamps invalid", (_label, value) => {
    const filters = parseEventFilterParams(params({ date_from: value }), NOW, VILNIUS);
    expect(filters.dateFrom).toEqual(new Date(DEFAULT_DATE_FROM));
    expect(filters.dateTo).toEqual(new Date(DEFAULT_DATE_TO));
  });

  it("serializes exact city-local midnight as a stable date-only value", () => {
    const filters: EventFilters = {
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: new Date("2026-10-24T21:00:00.000Z"),
      dateTo: new Date("2026-10-25T22:00:00.000Z")
    };

    const serialized = eventFiltersToSearchParams(
      filters,
      new URLSearchParams("keep=1"),
      VILNIUS
    );
    expect(serialized.get("date_from")).toBe("2026-10-25");
    expect(serialized.get("date_to")).toBe("2026-10-26");
    expect(serialized.get("keep")).toBe("1");
    expect(eventFilterParamsNeedNormalization(filters, serialized, VILNIUS)).toBe(false);
  });

  it("keeps non-midnight and later-fold bounds as full UTC ISO", () => {
    const nonMidnight: EventFilters = {
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: new Date("2026-06-08T07:00:00.000Z"),
      dateTo: new Date("2026-07-08T07:00:00.000Z")
    };
    const vilnius = eventFiltersToSearchParams(nonMidnight, undefined, VILNIUS);
    expect(vilnius.get("date_from")).toBe("2026-06-08T07:00:00.000Z");
    expect(vilnius.get("date_to")).toBe("2026-07-08T07:00:00.000Z");

    const laterFold: EventFilters = {
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: new Date("2026-11-01T06:30:00.000Z"),
      dateTo: new Date("2026-11-02T05:00:00.000Z")
    };
    const newYork = eventFiltersToSearchParams(laterFold, undefined, NEW_YORK);
    expect(newYork.get("date_from")).toBe("2026-11-01T06:30:00.000Z");
    expect(newYork.get("date_to")).toBe("2026-11-02");
    expect(
      eventFilterParamsNeedNormalization(laterFold, newYork, NEW_YORK)
    ).toBe(false);
  });

  it("compacts only the earlier repeated-midnight occurrence", () => {
    const timeZone = "America/Havana";
    const parsed = parseEventFilterParams(
      params({ date_from: "2026-11-01" }),
      NOW,
      timeZone
    );
    const earlier = new Date("2026-11-01T04:00:00.000Z");
    const later = new Date("2026-11-01T05:00:00.000Z");
    expect(parsed.dateFrom).toEqual(earlier);

    const base: EventFilters = {
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: earlier,
      dateTo: new Date("2026-12-01T05:00:00.000Z")
    };
    expect(eventFiltersToSearchParams(base, undefined, timeZone).get("date_from"))
      .toBe("2026-11-01");

    const laterFilters: EventFilters = { ...base, dateFrom: later };
    expect(eventFiltersToSearchParams(laterFilters, undefined, timeZone).get("date_from"))
      .toBe("2026-11-01T05:00:00.000Z");
  });

  it("compacts early supported years to zero-padded date-only values", () => {
    const filters: EventFilters = {
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: new Date("0002-01-01T22:18:44.000Z"),
      dateTo: new Date("0002-01-31T22:18:44.000Z")
    };
    const serialized = eventFiltersToSearchParams(filters, undefined, VILNIUS);
    expect(serialized.get("date_from")).toBe("0002-01-02");
    expect(serialized.get("date_to")).toBe("0002-02-01");
    expect(eventFilterParamsNeedNormalization(filters, serialized, VILNIUS)).toBe(false);
  });
});

describe("event filter URL serialization", () => {
  it("writes UTC bounds, sorted categories, and score, omitting empty values", () => {
    const paramsOut = eventFiltersToSearchParams({
      categories: ["music", "social"],
      minScore: 0.5,
      query: "jam",
      dateFrom: new Date("2026-06-08T07:00:00.000Z"),
      dateTo: new Date("2026-07-08T07:00:00.000Z")
    });

    expect(paramsOut.get("date_from")).toBe("2026-06-08T07:00:00.000Z");
    expect(paramsOut.get("date_to")).toBe("2026-07-08T07:00:00.000Z");
    expect(paramsOut.getAll("category")).toEqual(["music", "social"]);
    expect(paramsOut.get("min_score")).toBe("0.5");
    expect(paramsOut.get("q")).toBe("jam");
  });

  it("omits empty q, zero score, and no categories while keeping the bounds", () => {
    const paramsOut = eventFiltersToSearchParams({
      categories: [],
      minScore: 0,
      query: "",
      dateFrom: new Date("2026-06-08T07:00:00.000Z"),
      dateTo: new Date("2026-07-08T07:00:00.000Z")
    });

    expect(paramsOut.has("q")).toBe(false);
    expect(paramsOut.has("min_score")).toBe(false);
    expect(paramsOut.getAll("category")).toEqual([]);
    expect(paramsOut.get("date_from")).toBe("2026-06-08T07:00:00.000Z");
    expect(paramsOut.get("date_to")).toBe("2026-07-08T07:00:00.000Z");
  });

  it("preserves unrelated parameters while replacing owned ones", () => {
    const base = new URLSearchParams("keep=1&category=old&date_from=1999-01-01T00:00:00Z&q=old");
    const paramsOut = eventFiltersToSearchParams(
      {
        categories: ["social"],
        minScore: 0,
        query: "",
        dateFrom: new Date("2026-06-08T07:00:00.000Z"),
        dateTo: new Date("2026-07-08T07:00:00.000Z")
      },
      base
    );

    expect(paramsOut.get("keep")).toBe("1");
    expect(paramsOut.getAll("category")).toEqual(["social"]);
    expect(paramsOut.get("q")).toBe(null);
    expect(paramsOut.get("date_from")).toBe("2026-06-08T07:00:00.000Z");
  });

  it("does not mutate the provided base parameters", () => {
    const base = new URLSearchParams("keep=1&q=old");
    eventFiltersToSearchParams(
      {
        categories: [],
        minScore: 0,
        query: "new",
        dateFrom: new Date("2026-06-08T07:00:00.000Z"),
        dateTo: new Date("2026-07-08T07:00:00.000Z")
      },
      base
    );
    expect(base.get("q")).toBe("old");
  });

  it("removes only owned keys and reports their presence", () => {
    const base = new URLSearchParams("keep=1&category=social&min_score=0.5&q=x");
    const removed = removeEventFilterParams(base);
    expect(removed.get("keep")).toBe("1");
    expect(hasEventFilterParams(base)).toBe(true);
    expect(hasEventFilterParams(removed)).toBe(false);
  });
});

describe("event filter URL canonicalization", () => {
  const filters: EventFilters = {
    categories: ["music", "social"],
    minScore: 0,
    query: "",
    dateFrom: new Date("2026-06-08T07:00:00.000Z"),
    dateTo: new Date("2026-07-08T07:00:00.000Z")
  };

  it("flags a bare URL and non-canonical or default-equivalent owned parameters", () => {
    expect(eventFilterParamsNeedNormalization(filters, new URLSearchParams())).toBe(true);
    expect(
      eventFilterParamsNeedNormalization(
        filters,
        new URLSearchParams("category=social&category=music")
      )
    ).toBe(true);
    expect(
      eventFilterParamsNeedNormalization(
        filters,
        new URLSearchParams(
          "date_from=2026-06-08T07:00:00.000Z&date_to=2026-07-08T07:00:00.000Z&min_score=0"
        )
      )
    ).toBe(true);
  });

  it("accepts the canonical serialization and ignores unrelated parameters", () => {
    const canonical = eventFiltersToSearchParams(filters);
    expect(eventFilterParamsNeedNormalization(filters, canonical)).toBe(false);

    const withUnrelated = eventFiltersToSearchParams(filters, new URLSearchParams("keep=1"));
    expect(eventFilterParamsNeedNormalization(filters, withUnrelated)).toBe(false);
  });
});

describe("event filter normalization and equality", () => {
  it("applies safe intervals and canonical shapes to raw UI state", () => {
    const normalized = normalizeEventFilters({
      categories: [" b ", "a", "a", ""],
      minScore: 3,
      query: "x".repeat(MAX_EVENT_FILTER_QUERY_LENGTH + 5),
      dateFrom: new Date("2026-06-08T00:00:00Z"),
      dateTo: new Date("2026-06-01T00:00:00Z")
    });

    expect(normalized.categories).toEqual(["a", "b"]);
    expect(normalized.minScore).toBe(0);
    expect(normalized.query).toHaveLength(MAX_EVENT_FILTER_QUERY_LENGTH);
    expect(normalized.dateTo).toEqual(new Date("2026-07-08T00:00:00.000Z"));
  });

  it("treats equivalent resolved state as equal regardless of category order", () => {
    const a: EventFilters = {
      categories: ["a", "b"],
      minScore: 0.5,
      query: "q",
      dateFrom: new Date("2026-06-08T00:00:00Z"),
      dateTo: new Date("2026-07-08T00:00:00Z")
    };
    expect(eventFiltersEqual(a, { ...a })).toBe(true);
    expect(eventFiltersEqual(a, { ...a, dateTo: new Date("2026-07-09T00:00:00Z") })).toBe(false);
    expect(eventFiltersEqual(a, { ...a, query: "other" })).toBe(false);
    expect(eventFiltersEqual(a, { ...a, categories: ["b", "a"] })).toBe(false);
  });
});

function params(values: Record<string, string | string[]>): URLSearchParams {
  const search = new URLSearchParams();
  for (const [key, entries] of Object.entries(values)) {
    for (const entry of Array.isArray(entries) ? entries : [entries]) {
      search.append(key, entry);
    }
  }
  return search;
}
