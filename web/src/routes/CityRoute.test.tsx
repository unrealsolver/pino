import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import dayjs from "dayjs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryRouter } from "react-router-dom";

import { AppRoutes } from "../App";
import type { City, EventItem } from "../api";
import { theme } from "../theme";

vi.mock("./EventRoute/VirtualEventList", () => ({
  VirtualEventList: ({
    items
  }: {
    items: Array<{ key: string; type: string; occurrence?: { event: { title: string } } }>;
  }) => (
    <div data-testid="virtual-list">
      {items.map((item) =>
        item.type === "event" && item.occurrence ? (
          <div key={item.key}>{item.occurrence.event.title}</div>
        ) : null
      )}
    </div>
  )
}));

const CITIES: City[] = [
  {
    id: "lt/vilnius",
    country_code: "lt",
    slug: "vilnius",
    name: "Vilnius",
    timezone: "Europe/Vilnius"
  },
  {
    id: "zz/ny",
    country_code: "zz",
    slug: "ny",
    name: "New York",
    timezone: "America/New_York"
  }
];

const WINDOW_QUERY = "date_from=2026-06-01T00:00:00.000Z&date_to=2026-07-01T00:00:00.000Z";

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener() {},
    removeListener() {},
    addEventListener() {},
    removeEventListener() {},
    dispatchEvent() {
      return false;
    }
  }));
  vi.stubGlobal("scrollTo", vi.fn());
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("city route composition", () => {
  it.each(["/vilnius", "/lt/vilnius"])(
    "renders the same city feed at %s without changing the requested path",
    async (path) => {
      const fetchMock = mockApi();
      const { router } = renderApp([`${path}?${WINDOW_QUERY}`]);

      await screen.findByText("Events in Vilnius");
      expect(router.state.location.pathname).toBe(path);
      expect(await screen.findByText("lt/vilnius event")).toBeInTheDocument();
      const latestEvent = latestEventRequest(fetchMock);
      expect(latestEvent.searchParams.get("city")).toBe("lt/vilnius");
    }
  );

  it.each(["/", "/lt", "/event", "/event/"])(
    "replace-redirects %s to /vilnius and preserves query and hash",
    async (path) => {
      const fetchMock = mockApi();
      const { router } = renderApp([`${path}?${WINDOW_QUERY}&keep=1#section`]);

      await waitFor(() => expect(router.state.location.pathname).toBe("/vilnius"));
      expect(router.state.location.search).toBe(`?${WINDOW_QUERY}&keep=1`);
      expect(router.state.location.hash).toBe("#section");
      expect(router.state.historyAction).toBe("REPLACE");
      await screen.findByText("Events in Vilnius");
      expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("lt/vilnius");
    }
  );

  it.each(["/vilnius", "/lt/vilnius"])(
    "keeps the requested %s pathname through ordinary filter navigation",
    async (path) => {
      mockApi();
      const { router } = renderApp([`${path}?${WINDOW_QUERY}`]);

      await screen.findByText("Events in Vilnius");
      fireEvent.change(screen.getByLabelText("Text"), { target: { value: "music" } });

      await waitFor(() =>
        expect(new URLSearchParams(router.state.location.search).get("q")).toBe("music")
      );
      expect(router.state.location.pathname).toBe(path);
    }
  );

  it("normalizes known city paths to lowercase and no trailing slash with replace", async () => {
    mockApi();
    const shortRouter = renderApp(["/Vilnius/?keep=1#section"]).router;
    await waitFor(() => expect(shortRouter.state.location.pathname).toBe("/vilnius"));
    expect(shortRouter.state.location.search).toBe("?keep=1");
    expect(shortRouter.state.location.hash).toBe("#section");
    expect(shortRouter.state.historyAction).toBe("REPLACE");

    cleanup();
    const qualifiedRouter = renderApp(["/LT/Vilnius/?keep=1"]).router;
    await waitFor(() => expect(qualifiedRouter.state.location.pathname).toBe("/lt/vilnius"));
    expect(qualifiedRouter.state.location.search).toBe("?keep=1");
    expect(qualifiedRouter.state.historyAction).toBe("REPLACE");
  });

  it("shows not found for unknown countries and cities without fetching events", async () => {
    const fetchMock = mockApi();
    renderApp([`/ge/batumi?${WINDOW_QUERY}`]);

    expect(await screen.findByTestId("city-not-found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse Vilnius" })).toHaveAttribute("href", "/vilnius");
    expect(screen.queryByText(/Events in/)).not.toBeInTheDocument();
    expect(eventRequests(fetchMock)).toHaveLength(0);
  });

  it("keeps /batumi unknown unless it is explicitly aliased", async () => {
    const fetchMock = mockApi();
    renderApp([`/batumi?${WINDOW_QUERY}`]);

    expect(await screen.findByTestId("city-not-found")).toBeInTheDocument();
    expect(eventRequests(fetchMock)).toHaveLength(0);
  });

  it("distinguishes metadata failure from not found and retries", async () => {
    let cityRequests = 0;
    const fetchMock = mockApi({
      cityResponse: () => {
        cityRequests += 1;
        return cityRequests === 1
          ? jsonResponse({ detail: "Metadata outage" }, 503)
          : jsonResponse({ cities: CITIES });
      }
    });
    renderApp([`/lt/vilnius?${WINDOW_QUERY}`]);

    expect(await screen.findByText("City metadata unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("city-not-found")).not.toBeInTheDocument();
    expect(eventRequests(fetchMock)).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await screen.findByText("Events in Vilnius");
    expect(cityRequests).toBe(2);
    expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("lt/vilnius");
  });

  it("does not fetch an unscoped event feed while city metadata is pending", async () => {
    let resolveCities!: (response: Response) => void;
    const pendingCities = new Promise<Response>((resolve) => {
      resolveCities = resolve;
    });
    const fetchMock = mockApi({ cityResponse: () => pendingCities });
    renderApp([`/lt/vilnius?${WINDOW_QUERY}`]);

    await waitFor(() => expect(cityRequests(fetchMock)).toHaveLength(1));
    expect(eventRequests(fetchMock)).toHaveLength(0);
    expect(screen.getByText(/Loading city/)).toBeInTheDocument();
    expect(screen.queryByText(/Events in/)).not.toBeInTheDocument();

    resolveCities(jsonResponse({ cities: CITIES }));
    await screen.findByText("Events in Vilnius");
    expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("lt/vilnius");
  });

  it("separates city requests and cache keys and restores both with Back and Forward", async () => {
    const fetchMock = mockApi();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } }
    });
    const { router } = renderApp(
      [`/lt/vilnius?${WINDOW_QUERY}`, `/zz/ny?${WINDOW_QUERY}`],
      { queryClient, initialIndex: 1 }
    );

    await screen.findByText("Events in New York");
    expect(await screen.findByText("zz/ny event")).toBeInTheDocument();
    expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("zz/ny");

    await act(async () => {
      await router.navigate(-1);
    });
    await screen.findByText("Events in Vilnius");
    expect(await screen.findByText("lt/vilnius event")).toBeInTheDocument();
    expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("lt/vilnius");

    await act(async () => {
      await router.navigate(1);
    });
    await screen.findByText("Events in New York");
    expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("zz/ny");

    const eventKeys = queryClient
      .getQueryCache()
      .findAll({ queryKey: ["events"] })
      .map((query) => query.queryKey);
    expect(eventKeys).toEqual(
      expect.arrayContaining([
        ["events", "lt/vilnius", expect.objectContaining({ categories: [] })],
        ["events", "zz/ny", expect.objectContaining({ categories: [] })]
      ])
    );
  });

  it("never displays the previous city's events while a new city loads", async () => {
    let resolveNewYork!: (response: Response) => void;
    const pendingNewYork = new Promise<Response>((resolve) => {
      resolveNewYork = resolve;
    });
    const fetchMock = mockApi({
      eventResponse: (url) => {
        const city = url.searchParams.get("city");
        if (city === "zz/ny") {
          return pendingNewYork;
        }
        return defaultEventResponse(url);
      }
    });
    const { router } = renderApp([`/lt/vilnius?${WINDOW_QUERY}`]);

    await screen.findByText("lt/vilnius event");
    await act(async () => {
      await router.navigate(`/zz/ny?${WINDOW_QUERY}`);
    });

    await waitFor(() => expect(latestEventRequest(fetchMock).searchParams.get("city")).toBe("zz/ny"));
    expect(screen.queryByText("lt/vilnius event")).not.toBeInTheDocument();
    expect(screen.getByText("Events in New York")).toBeInTheDocument();

    resolveNewYork(defaultEventResponse(latestEventRequest(fetchMock)));
    expect(await screen.findByText("zz/ny event")).toBeInTheDocument();
  });

  it("shows an empty result without treating it as not found", async () => {
    mockApi({
      eventResponse: () =>
        jsonResponse({ timezone: "Europe/Vilnius", categories: [], events: [] })
    });
    renderApp([`/lt/vilnius?${WINDOW_QUERY}`]);

    expect(await screen.findByText("No events match these filters.")).toBeInTheDocument();
    expect(screen.queryByTestId("city-not-found")).not.toBeInTheDocument();
  });
});

describe("city timezone display and picker edits", () => {
  it.each(["From", "To"])("normalizes invalid URL filters on an unchanged %s action using replace", async (field) => {
    const fetchMock = mockApi();
    const { router } = renderApp([
      "/vilnius?keep=previous",
      "/vilnius?date_from=2026-06-01T00%3A00%3A00.000Z&date_to=bad&keep=1"
    ]);
    await screen.findByText("Events in Vilnius");
    await waitFor(() => expect(eventRequests(fetchMock)).toHaveLength(1));
    if (field === "To") {
      fireEvent.click(screen.getByRole("button", { name: "Clear To" }));
    } else {
      fireEvent.click(screen.getByLabelText("From"));
      fireEvent.click(await screen.findByRole("button", { name: "1 June 2026" }));
    }
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("date_to"))
      .toBe("2026-07-01T00:00:00.000Z"));
    expect(new URLSearchParams(router.state.location.search).get("keep")).toBe("1");
    expect(eventRequests(fetchMock)).toHaveLength(1);
    await act(async () => { await router.navigate(-1); });
    expect(router.state.location.search).toBe("?keep=previous");
  });

  it("edits supported early years without the calendar converting them to the 1900s", async () => {
    const fetchMock = mockApi();
    const { router } = renderApp([
      "/lt/vilnius?date_from=0002-01-02T12%3A00%3A00.000Z&date_to=0002-02-01T12%3A00%3A00.000Z"
    ]);
    await screen.findByText("Events in Vilnius");
    fireEvent.click(screen.getByLabelText("From"));
    expect(screen.getByLabelText("From date")).toHaveValue("0002-01-02");
    fireEvent.change(screen.getByLabelText("From date"), { target: { value: "0002-01-03" } });
    await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("date_from"))
      .toMatch(/^0002-01-03T/));
    expect(latestEventRequest(fetchMock).searchParams.get("date_from")).toMatch(/^0002-01-03T/);
    expect(screen.getByLabelText("From date")).toHaveValue("0002-01-03");
  });

  it("uses city-local defaults and picker values around midnight", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-06-08T21:30:00.000Z"));
    const fetchMock = mockApi();
    const { router } = renderApp(["/lt/vilnius?keep=1"]);

    await screen.findByText("Events in Vilnius");
    await waitFor(() => expect(eventRequests(fetchMock)).toHaveLength(1));
    const request = latestEventRequest(fetchMock);
    expect(request.searchParams.get("date_from")).toBe("2026-06-08T21:00:00.000Z");
    expect(request.searchParams.get("date_to")).toBe("2026-07-08T21:00:00.000Z");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-06-09 00:00");

    fireEvent.click(screen.getByLabelText("From"));
    const targetDay = new Date("2026-07-01T12:00:00.000Z");
    fireEvent.click(
      await screen.findByRole("button", { name: dayjs(targetDay).format("D MMMM YYYY") })
    );

    await waitFor(() =>
      expect(latestEventRequest(fetchMock).searchParams.get("date_from"))
        .toBe("2026-06-30T21:00:00.000Z")
    );
    const edited = latestEventRequest(fetchMock);
    expect(edited.searchParams.get("date_to")).toBe("2026-07-30T21:00:00.000Z");
    expect(edited.searchParams.get("city")).toBe("lt/vilnius");
    expect(new URLSearchParams(router.state.location.search).get("date_from"))
      .toBe("2026-07-01");
  });

  it.each([
    {
      label: "spring DST",
      dateFrom: "2026-03-01T05:00:00.000Z",
      defaultTo: "2026-03-31T04:00:00.000Z",
      nextMonthTo: "2026-04-30T04:00:00.000Z"
    },
    {
      label: "fall DST",
      dateFrom: "2026-10-10T04:00:00.000Z",
      defaultTo: "2026-11-09T05:00:00.000Z",
      nextMonthTo: "2026-12-09T05:00:00.000Z"
    }
  ])("keeps calendar-day defaults across $label", async (row) => {
    const fetchMock = mockApi();
    renderApp([
      `/zz/ny?date_from=${encodeURIComponent(row.dateFrom)}&keep=1`
    ]);

    await screen.findByText("Events in New York");
    await waitFor(() =>
      expect(latestEventRequest(fetchMock).searchParams.get("date_to")).toBe(row.defaultTo)
    );

    fireEvent.click(await screen.findByRole("button", { name: "Next month" }));
    await waitFor(() =>
      expect(latestEventRequest(fetchMock).searchParams.get("date_to")).toBe(row.nextMonthTo)
    );
    expect(latestEventRequest(fetchMock).searchParams.get("date_from")).toBe(row.dateFrom);
  });

  it("keeps a city-valid Vilnius spring wall time without browser DST normalization", async () => {
    const fetchMock = mockApi();
    const url =
      `/lt/vilnius?date_from=${encodeURIComponent("2026-03-08T00:30:00.000Z")}` +
      `&date_to=${encodeURIComponent("2026-03-10T00:00:00.000Z")}`;
    const { router } = renderApp([url]);

    await screen.findByText("Events in Vilnius");
    // 2026-03-08 02:30 is valid in Vilnius but a DST gap in a New York browser.
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-03-08 02:30");

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.change(screen.getByLabelText("From time"), { target: { value: "02:45" } });

    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("date_from"))
        .toBe("2026-03-08T00:45:00.000Z")
    );
    expect(latestEventRequest(fetchMock).searchParams.get("date_from"))
      .toBe("2026-03-08T00:45:00.000Z");
  });

  it("rejects a Vilnius spring gap even when the browser wall time is valid", async () => {
    const fetchMock = mockApi();
    const url =
      `/lt/vilnius?date_from=${encodeURIComponent("2026-03-29T02:30:00.000Z")}` +
      `&date_to=${encodeURIComponent("2026-03-30T00:00:00.000Z")}&keep=1`;
    const { router } = renderApp([url]);

    await screen.findByText("Events in Vilnius");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-03-29 05:30");
    const keyBefore = router.state.location.key;
    const requestsBefore = eventRequests(fetchMock).length;

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.change(screen.getByLabelText("From time"), { target: { value: "03:30" } });

    expect(await screen.findByText(/does not exist in Vilnius/)).toBeInTheDocument();
    expect(router.state.location.key).toBe(keyBefore);
    expect(eventRequests(fetchMock)).toHaveLength(requestsBefore);
  });

  it("clears a rejected picker time on Reset even when filters are already default", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-03-29T10:00:00.000Z"));
    const fetchMock = mockApi();
    const { router } = renderApp(["/vilnius?keep=1"]);

    await screen.findByText("Events in Vilnius");
    const keyBefore = router.state.location.key;
    const requestsBefore = eventRequests(fetchMock).length;
    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.change(screen.getByLabelText("From time"), { target: { value: "03:30" } });
    expect(await screen.findByText(/does not exist in Vilnius/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.queryByText(/does not exist in Vilnius/)).not.toBeInTheDocument();
    expect(router.state.location.key).toBe(keyBefore);
    expect(router.state.location.search).toBe("?keep=1");
    expect(eventRequests(fetchMock)).toHaveLength(requestsBefore);
  });

  it("rejects a nonexistent spring-forward picker time without navigating", async () => {
    const fetchMock = mockApi();
    const url =
      `/zz/ny?date_from=${encodeURIComponent("2026-03-08T07:00:00.000Z")}` +
      `&date_to=${encodeURIComponent("2026-03-09T04:00:00.000Z")}&keep=1`;
    const { router } = renderApp([url]);

    await screen.findByText("Events in New York");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-03-08 03:00");
    const keyBefore = router.state.location.key;
    const requestsBefore = eventRequests(fetchMock).length;

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.change(screen.getByLabelText("From time"), { target: { value: "02:30" } });

    expect(await screen.findByText(/does not exist in New York/)).toBeInTheDocument();
    expect(router.state.location.key).toBe(keyBefore);
    expect(router.state.location.search).toContain("2026-03-08T07%3A00%3A00.000Z");
    expect(eventRequests(fetchMock)).toHaveLength(requestsBefore);

    fireEvent.change(screen.getByLabelText("From time"), { target: { value: "04:00" } });
    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("date_from"))
        .toBe("2026-03-08T08:00:00.000Z")
    );
    expect(screen.queryByText(/does not exist in New York/)).not.toBeInTheDocument();
  });

  it("chooses the earlier instant for a newly ambiguous fall-back wall time", async () => {
    const fetchMock = mockApi();
    const url =
      `/zz/ny?date_from=${encodeURIComponent("2026-11-01T07:30:00.000Z")}` +
      `&date_to=${encodeURIComponent("2026-11-02T05:00:00.000Z")}`;
    const { router } = renderApp([url]);

    await screen.findByText("Events in New York");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-11-01 02:30");

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.change(screen.getByLabelText("From time"), { target: { value: "01:30" } });

    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("date_from"))
        .toBe("2026-11-01T05:30:00.000Z")
    );
    expect(latestEventRequest(fetchMock).searchParams.get("date_from"))
      .toBe("2026-11-01T05:30:00.000Z");
  });

  it("preserves a URL-selected later overlap instant when the picker re-emits it", async () => {
    mockApi();
    const url =
      `/zz/ny?date_from=${encodeURIComponent("2026-11-01T06:30:00.000Z")}` +
      `&date_to=2026-11-02`;
    const { router } = renderApp([url]);

    await screen.findByText("Events in New York");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-11-01 01:30");
    const keyBefore = router.state.location.key;

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.click(
      await screen.findByRole("button", { name: "1 November 2026" })
    );

    await waitFor(() =>
      expect((screen.getByLabelText("From") as HTMLInputElement).value)
        .toBe("2026-11-01 01:30")
    );
    expect(router.state.location.key).toBe(keyBefore);
    expect(new URLSearchParams(router.state.location.search).get("date_from"))
      .toBe("2026-11-01T06:30:00.000Z");
  });
});

describe("city date-only filter URLs", () => {
  it("sends date-only bounds as full ISO and shares cache identity across aliases and spellings", async () => {
    const fetchMock = mockApi();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } }
    });
    const dateOnly =
      "/lt/vilnius?date_from=2026-10-25&date_to=2026-10-26&keep=1#section";
    const explicit =
      `/vilnius?date_from=${encodeURIComponent("2026-10-24T21:00:00.000Z")}` +
      `&date_to=${encodeURIComponent("2026-10-25T22:00:00.000Z")}&keep=1#section`;
    const { router } = renderApp([dateOnly, explicit], { queryClient, initialIndex: 0 });

    await screen.findByText("Events in Vilnius");
    await waitFor(() => expect(eventRequests(fetchMock)).toHaveLength(1));
    const request = latestEventRequest(fetchMock);
    expect(request.searchParams.get("city")).toBe("lt/vilnius");
    expect(request.searchParams.get("date_from")).toBe("2026-10-24T21:00:00.000Z");
    expect(request.searchParams.get("date_to")).toBe("2026-10-25T22:00:00.000Z");

    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() => expect(router.state.location.pathname).toBe("/vilnius"));
    await screen.findByText("Events in Vilnius");
    // The equivalent explicit-instant spelling reuses the same resolved cache entry.
    expect(eventRequests(fetchMock)).toHaveLength(1);
    const eventKeys = queryClient
      .getQueryCache()
      .findAll({ queryKey: ["events"] })
      .map((query) => query.queryKey);
    expect(eventKeys).toEqual([
      [
        "events",
        "lt/vilnius",
        expect.objectContaining({
          dateFrom: "2026-10-24T21:00:00.000Z",
          dateTo: "2026-10-25T22:00:00.000Z"
        })
      ]
    ]);
  });

  it("keeps canonical date-only midnight stable on an unchanged picker action", async () => {
    mockApi();
    const { router } = renderApp([
      "/vilnius?keep=1&date_from=2026-10-25&date_to=2026-11-24#section"
    ]);
    await screen.findByText("Events in Vilnius");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-25 00:00");
    const keyBefore = router.state.location.key;

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.click(await screen.findByRole("button", { name: "25 October 2026" }));

    await waitFor(() =>
      expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-25 00:00")
    );
    expect(router.state.location.key).toBe(keyBefore);
    expect(router.state.location.search).toBe(
      "?keep=1&date_from=2026-10-25&date_to=2026-11-24"
    );
    expect(router.state.location.hash).toBe("#section");
  });

  it("keeps non-midnight bounds as UTC ISO while compacting a midnight To with replace", async () => {
    const fetchMock = mockApi();
    const { router } = renderApp([
      `/vilnius?date_from=${encodeURIComponent("2026-06-08T07:00:00.000Z")}` +
        `&date_to=${encodeURIComponent("2026-07-08T21:00:00.000Z")}&keep=1`
    ]);
    await screen.findByText("Events in Vilnius");
    await waitFor(() => expect(eventRequests(fetchMock)).toHaveLength(1));
    const keyBefore = router.state.location.key;

    fireEvent.click(screen.getByLabelText("From"));
    fireEvent.click(await screen.findByRole("button", { name: "8 June 2026" }));

    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("date_to")).toBe("2026-07-09")
    );
    expect(new URLSearchParams(router.state.location.search).get("date_from")).toBe(
      "2026-06-08T07:00:00.000Z"
    );
    expect(router.state.location.search).toContain("keep=1");
    expect(router.state.historyAction).toBe("REPLACE");
    expect(router.state.location.key).not.toBe(keyBefore);
    expect(eventRequests(fetchMock)).toHaveLength(1);
  });
});

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } }
  });
}

function renderApp(
  initialEntries: string[],
  options: { queryClient?: QueryClient; initialIndex?: number } = {}
) {
  const queryClient = options.queryClient ?? createQueryClient();
  const router = createMemoryRouter([{ path: "*", element: <AppRoutes /> }], {
    initialEntries,
    initialIndex: options.initialIndex ?? initialEntries.length - 1
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <DatesProvider settings={{ locale: "en", firstDayOfWeek: 1, weekendDays: [0, 6] }}>
          <RouterProvider router={router} />
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
  return { router, queryClient, ...view };
}

type MockApiOptions = {
  cityResponse?: (url: URL) => Response | Promise<Response>;
  eventResponse?: (url: URL) => Response | Promise<Response>;
};

function mockApi(options: MockApiOptions = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/cities") {
      return options.cityResponse
        ? await options.cityResponse(url)
        : jsonResponse({ cities: CITIES });
    }
    if (url.pathname === "/api/events") {
      return options.eventResponse ? await options.eventResponse(url) : defaultEventResponse(url);
    }
    throw new Error(`Unexpected request ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function cityRequests(fetchMock: ReturnType<typeof vi.fn>) {
  return apiRequests(fetchMock, "/api/cities");
}

function eventRequests(fetchMock: ReturnType<typeof vi.fn>) {
  return apiRequests(fetchMock, "/api/events");
}

function apiRequests(fetchMock: ReturnType<typeof vi.fn>, pathname: string) {
  return fetchMock.mock.calls
    .map((call) => new URL(String(call[0]), "http://localhost"))
    .filter((url) => url.pathname === pathname);
}

function latestEventRequest(fetchMock: ReturnType<typeof vi.fn>): URL {
  const requests = eventRequests(fetchMock);
  const latest = requests.at(-1);
  if (!latest) {
    throw new Error("No event request was made");
  }
  return latest;
}

function defaultEventResponse(url: URL): Response {
  const city = url.searchParams.get("city") ?? "lt/vilnius";
  const dateFrom = url.searchParams.get("date_from") ?? "2026-06-10T10:00:00.000Z";
  return jsonResponse({
    timezone: city === "zz/ny" ? "America/New_York" : "Europe/Vilnius",
    categories: ["music"],
    events: [
      event({
        starts_at: dateFrom,
        relevant_from: dateFrom,
        occurrence_id: `${city}:${dateFrom}`,
        title: `${city} event`
      })
    ]
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" }
  });
}

function event(overrides: Partial<EventItem> = {}): EventItem {
  return {
    refinement_id: overrides.refinement_id ?? "event",
    occurrence_id: "event:occurrence",
    title: "event",
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
