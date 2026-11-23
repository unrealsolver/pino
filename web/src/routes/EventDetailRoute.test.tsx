import { QueryClient } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { AppProviders, AppRoutes } from "../App";
import type { EventDetail } from "../api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("opens a direct event URL and shows its schedule index without loading the list", async () => {
  const event: EventDetail = {
    refinement_id: "refinement-1",
    record_id: "record-1",
    source_event_id: null,
    source_kind: "event",
    title: "Synth jam",
    source_title: null,
    summary: "Synth jam",
    text: "A Monday session.",
    source: "fixture",
    url: null,
    images: [],
    location: null,
    city_id: "lt/vilnius",
    timezone: "Europe/Vilnius",
    published_at: null,
    captured_at: "2020-01-01T00:00:00Z",
    refined_at: "2020-01-01T00:00:00Z",
    relevant_from: null,
    relevant_to: null,
    schedule: { kind: "recurrence" },
    weekly_multirange: "{[1140,1261)}",
    category_scores: {}
  };
  const fetchMock = vi.fn(async () => Response.json(event));
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("scrollTo", vi.fn());
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  }));

  render(
    <AppProviders queryClient={new QueryClient()}>
      <MemoryRouter initialEntries={["/event/refinement-1"]}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>
  );

  expect(await screen.findByRole("heading", { name: "Synth jam" })).toBeInTheDocument();
  expect(screen.getByText("A Monday session.")).toBeInTheDocument();
  expect(screen.getByText("{[1140,1261)}")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledExactlyOnceWith("/api/events/refinement-1", expect.anything());
});
