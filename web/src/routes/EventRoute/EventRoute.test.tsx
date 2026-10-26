import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import dayjs from "dayjs";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryRouter, useLocation } from "react-router-dom";

import type { City, EventItem } from "../../api";
import { addDays, defaultDateTo, todayMorning } from "../../eventUtils";
import { theme } from "../../theme";
import { EventRoute } from "./EventRoute";

const CITY: City = {
  id: "lt/vilnius",
  country_code: "lt",
  slug: "vilnius",
  name: "Vilnius",
  timezone: "Europe/Vilnius"
};

vi.mock("./VirtualEventList", () => ({
  VirtualEventList: ({ items }: { items: Array<{ key: string }> }) => (
    <div data-testid="virtual-list">{items.length}</div>
  )
}));

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
});

describe("EventRoute URL synchronization", () => {
  it("refreshes the implicit default window after midnight when Reset is pressed", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    try {
      vi.setSystemTime(new Date("2026-06-08T23:59:00+03:00"));
      const fetchMock = mockEvents([event()]);
      renderRoute(["/event/?keep=1#section"]);
      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      expect(requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("date_from"))
        .toBe("2026-06-07T21:00:00.000Z");

      vi.setSystemTime(new Date("2026-06-09T00:01:00+03:00"));
      fireEvent.click(screen.getByRole("button", { name: "Reset" }));
      await waitFor(() => expect(
        requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("date_from")
      ).toBe("2026-06-08T21:00:00.000Z"));
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses the initial URL for both the controls and the request", async () => {
    const fetchMock = mockEvents([event()], ["music", "social"]);
    renderRoute([`/event/?${WINDOW_QUERY}&category=social&category=music&min_score=0.4&q=jam`]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const requested = requestedUrl(fetchMock.mock.calls[0][0]);
    expect(requested.searchParams.get("date_from")).toBe("2026-06-01T00:00:00.000Z");
    expect(requested.searchParams.get("date_to")).toBe("2026-07-01T00:00:00.000Z");
    expect(requested.searchParams.getAll("category")).toEqual(["music", "social"]);
    expect(requested.searchParams.get("min_score")).toBe("0.4");
    expect(requested.searchParams.get("q")).toBe("jam");

    expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("jam");
    expect((screen.getByLabelText("Score") as HTMLInputElement).value).toBe("0.4");
  });

  it("requests date-only URL bounds as full ISO instants", async () => {
    const fetchMock = mockEvents([event()]);
    const { router } = renderRoute([
      "/event/?date_from=2026-10-25&date_to=2026-10-26&keep=1#section"
    ]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const requested = requestedUrl(fetchMock.mock.calls[0][0]);
    expect(requested.searchParams.get("date_from")).toBe("2026-10-24T21:00:00.000Z");
    expect(requested.searchParams.get("date_to")).toBe("2026-10-25T22:00:00.000Z");
    expect(router.state.location.search).toContain("keep=1");
    expect(router.state.location.hash).toBe("#section");
    expect((screen.getByLabelText("From") as HTMLInputElement).value).toBe("2026-10-25 00:00");
  });

  it("pushes one entry and refetches when a category is selected", async () => {
    const fetchMock = mockEvents([event()], ["music", "social"]);
    const { router } = renderRoute([`/event/?${WINDOW_QUERY}`]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await screen.findByTestId("virtual-list");

    const input = screen
      .getAllByLabelText("Tags")
      .find((element) => element.tagName === "INPUT") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.mouseDown(input);
    fireEvent.click(input);
    fireEvent.click(await screen.findByRole("option", { name: "music" }));

    await waitFor(() => expect(router.state.location.search).toContain("category=music"));
    expect(requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.getAll("category")).toEqual([
      "music"
    ]);
  });

  it("updates the URL and request on a text edit using replace navigation", async () => {
    const fetchMock = mockEvents([event()]);
    const { router } = renderRoute([
      `/event/?${WINDOW_QUERY}`,
      `/event/?${WINDOW_QUERY}&q=first`
    ]);

    await waitFor(() =>
      expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("first")
    );
    fireEvent.change(screen.getByLabelText("Text"), { target: { value: "live music" } });

    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("q")).toBe("live music")
    );
    expect(requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("q")).toBe(
      "live music"
    );
    expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("live music");

    // Replace navigation means Back skips the previous (q=first) entry entirely.
    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() =>
      expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("")
    );
  });

  it("pushes one entry for Next month and Back restores the previous window", async () => {
    const fetchMock = mockEvents([event()]);
    const { router } = renderRoute(["/event/", `/event/?${WINDOW_QUERY}`]);
    const nextMonth = await screen.findByRole("button", { name: "Next month" });

    fireEvent.click(nextMonth);
    await waitFor(() =>
      expect(router.state.location.search).toContain(
        "date_to=2026-07-31T00%3A00%3A00.000Z"
      )
    );
    expect(requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("date_to")).toBe(
      "2026-07-31T00:00:00.000Z"
    );

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(router.state.location.search).toContain("2026-07-01"));
  });

  it("resets owned keys while preserving unrelated parameters and the fragment", async () => {
    const fetchMock = mockEvents([event()]);
    const { router, navigations } = renderRoute([
      `/event/?${WINDOW_QUERY}&category=social&q=x&keep=1#section`
    ]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const beforeReset = navigations.length;

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    await waitFor(() => expect(router.state.location.search).toBe("?keep=1"));
    expect(router.state.location.hash).toBe("#section");
    expect(navigations.length).toBe(beforeReset + 1);
    const requested = requestedUrl(fetchMock.mock.calls.at(-1)?.[0]);
    expect(requested.searchParams.getAll("category")).toEqual([]);
    expect(requested.searchParams.has("q")).toBe(false);
    expect(requested.searchParams.has("min_score")).toBe(false);

    // Reset pushes, so Back returns to the filtered entry.
    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(router.state.location.search).toContain("category=social"));
  });

  it("does not navigate or refetch when Reset is a no-op", async () => {
    const fetchMock = mockEvents([event()]);
    const { router, navigations } = renderRoute(["/event/?keep=1"]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const beforeReset = navigations.length;

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    expect(router.state.location.search).toBe("?keep=1");
    expect(navigations.length).toBe(beforeReset);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("replaces rather than pushes when Reset leaves effective filters unchanged", async () => {
    const fetchMock = mockEvents([event()]);
    const dateFrom = todayMorning();
    const dateTo = defaultDateTo(dateFrom);
    const defaultOwned =
      `date_from=${encodeURIComponent(dateFrom.toISOString())}` +
      `&date_to=${encodeURIComponent(dateTo.toISOString())}&min_score=0`;
    const { router, navigations } = renderRoute([
      "/event/?keep=origin-a",
      `/event/?keep=origin-b&${defaultOwned}`
    ]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const beforeReset = navigations.length;

    fireEvent.click(screen.getByRole("button", { name: "Reset" }));

    await waitFor(() => expect(router.state.location.search).toBe("?keep=origin-b"));
    expect(navigations.length).toBe(beforeReset + 1);

    // A replace leaves no extra entry, so Back returns to the earlier origin entry.
    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(router.state.location.search).toBe("?keep=origin-a"));
  });

  it("replaces rather than pushes when a no-op action canonicalizes owned parameters", async () => {
    const fetchMock = mockEvents([event()]);
    const longQuery = "x".repeat(200);
    const { router, navigations } = renderRoute([
      "/event/?keep=origin-a",
      `/event/?keep=origin-b&${WINDOW_QUERY}&category=b&category=a&q=${longQuery}`
    ]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const beforeEdit = navigations.length;

    // A 201st character is capped back to 200, so the effective filters do not change.
    fireEvent.change(screen.getByLabelText("Text"), {
      target: { value: `${longQuery}y` }
    });

    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).getAll("category")).toEqual([
        "a",
        "b"
      ])
    );
    expect(navigations.length).toBe(beforeEdit + 1);

    // Replace leaves no extra entry, so Back returns to the earlier origin entry.
    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(router.state.location.search).toBe("?keep=origin-a"));
  });

  it("restores controls and the request on Back and Forward", async () => {
    const fetchMock = mockEvents([event()]);
    const { router } = renderRoute([
      `/event/?${WINDOW_QUERY}`,
      `/event/?${WINDOW_QUERY}&q=first`
    ]);

    await waitFor(() =>
      expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("first")
    );

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() =>
      expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("")
    );
    expect(
      fetchMock.mock.calls.some((call) => requestedUrl(call[0]).searchParams.has("q"))
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some((call) => !requestedUrl(call[0]).searchParams.has("q"))
    ).toBe(true);

    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() =>
      expect((screen.getByLabelText("Text") as HTMLInputElement).value).toBe("first")
    );
  });

  it("updates both date bounds in one history entry when From changes", async () => {
    const fetchMock = mockEvents([event()]);
    const { router, navigations } = renderRoute(["/event/?q=jam"]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const start = todayMorning();
    const initial = screen.getByLabelText("From");
    fireEvent.click(initial);
    const targetDay = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 2);
    const label = dayjs(targetDay).format("D MMMM YYYY");
    const before = navigations.length;
    fireEvent.click(await screen.findByRole("button", { name: label }));

    await waitFor(() => expect(navigations).toHaveLength(before + 1));
    expect(router.state.historyAction).toBe("PUSH");
    const requested = requestedUrl(fetchMock.mock.calls.at(-1)?.[0]);
    expect(requested.searchParams.get("date_from")).toBe(targetDay.toISOString());
    expect(requested.searchParams.get("date_to")).toBe(addDays(targetDay, 30).toISOString());
    expect(requested.searchParams.get("q")).toBe("jam");
  });

  it("pushes an edited To date and restores it with Back", async () => {
    const fetchMock = mockEvents([event()]);
    const { router } = renderRoute(["/event/"]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    const targetDay = addDays(defaultDateTo(todayMorning()), 2);
    fireEvent.click(screen.getByLabelText("To"));
    fireEvent.click(await screen.findByRole("button", {
      name: dayjs(targetDay).format("D MMMM YYYY")
    }));
    await waitFor(() => expect(router.state.historyAction).toBe("PUSH"));
    expect(requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("date_to"))
      .toBe(targetDay.toISOString());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(
      requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("date_to")
    ).toBe(defaultDateTo(todayMorning()).toISOString()));
  });

  it("pushes a score edit and requests the matching score", async () => {
    const fetchMock = mockEvents([event()]);
    const { router } = renderRoute(["/event/"]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText("Score"), { target: { value: "0.6" } });
    await waitFor(() => expect(
      requestedUrl(fetchMock.mock.calls.at(-1)?.[0]).searchParams.get("min_score")
    ).toBe("0.6"));
    expect(router.state.historyAction).toBe("PUSH");
  });
});

function renderRoute(initialEntries: string[], initialIndex = initialEntries.length - 1) {
  const navigations: string[] = [];
  function NavigationProbe() {
    const location = useLocation();
    useEffect(() => {
      navigations.push(location.search);
    }, [location]);
    return null;
  }

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } }
  });
  const router = createMemoryRouter(
    [
      {
        path: "/event/",
        element: (
          <>
            <EventRoute city={CITY} />
            <NavigationProbe />
          </>
        )
      }
    ],
    { initialEntries, initialIndex }
  );
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <DatesProvider settings={{ locale: "en", firstDayOfWeek: 1, weekendDays: [0, 6] }}>
          <RouterProvider router={router} />
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
  return { router, navigations, ...view };
}

function mockEvents(events: EventItem[], categories: string[] = ["music", "social"]) {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify({ timezone: "Europe/Vilnius", categories, events }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      })
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function requestedUrl(input: unknown): URL {
  return new URL(String(input), "http://localhost");
}

function event(overrides: Partial<EventItem> = {}): EventItem {
  return {
    refinement_id: "event",
    occurrence_id: "event:2026-06-10T0700",
    title: "Event",
    source: "test",
    url: null,
    location: null,
    starts_at: "2026-06-10T07:00:00.000Z",
    ends_at: null,
    relevant_from: "2026-06-10T07:00:00.000Z",
    relevant_to: null,
    category_scores: {},
    matching_score: 0,
    ...overrides
  };
}
