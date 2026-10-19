import { Alert, Button, Container, Group, Loader, Paper, Stack, Text } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { eventQueryKey, fetchEvents, type EventFilters } from "../../api";
import {
  eventFilterParamsNeedNormalization,
  eventFiltersEqual,
  eventFiltersToSearchParams,
  hasEventFilterParams,
  normalizeEventFilters,
  parseEventFilterParams,
  removeEventFilterParams
} from "../../eventFilterUrl";
import { defaultDateTo, groupEventsByDay, todayMorning } from "../../eventUtils";
import { EventFiltersForm } from "./EventFiltersForm";
import classes from "./EventRoute.module.css";
import { EventHeader } from "./EventHeader";
import { VirtualEventList } from "./VirtualEventList";
import { buildListRevision, buildVirtualListItems } from "./utils";

export function EventRoute() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  // The URL is the single authoritative filter state; controls read it directly.
  const filters = useMemo(() => parseEventFilterParams(searchParams), [searchParams, location.key]);

  const [hiddenEventIdList, setHiddenEventIdList] = useLocalStorage<string[]>({
    key: "pino-web-hidden-event-ids",
    defaultValue: []
  });
  const [showHidden, setShowHidden] = useLocalStorage({
    key: "pino-web-show-hidden-events",
    defaultValue: false
  });
  const eventsQuery = useQuery({
    queryKey: eventQueryKey(filters),
    queryFn: ({ signal }) => fetchEvents(filters, { signal }),
    placeholderData: keepPreviousData
  });

  const categories = eventsQuery.data?.categories ?? [];
  const calendarWindowEnd = useMemo(
    () => filters.dateTo ?? defaultDateTo(filters.dateFrom),
    [filters.dateFrom, filters.dateTo]
  );
  const days = useMemo(
    () => groupEventsByDay(eventsQuery.data?.events ?? [], filters.dateFrom, calendarWindowEnd),
    [calendarWindowEnd, eventsQuery.data?.events, filters.dateFrom]
  );
  const hiddenEventIds = useMemo(() => new Set(hiddenEventIdList), [hiddenEventIdList]);
  const listItems = useMemo(
    () => buildVirtualListItems(days, hiddenEventIds, showHidden),
    [days, hiddenEventIds, showHidden]
  );
  const listRevision = useMemo(() => buildListRevision(listItems), [listItems]);
  const visibleEventCount = (
    eventsQuery.data?.events.filter((event) => !hiddenEventIds.has(event.refinement_id)) ?? []
  ).length;
  const errorMessage = eventsQuery.error instanceof Error
    ? eventsQuery.error.message
    : "Could not load events";
  const hasLoadedData = Boolean(eventsQuery.data);
  const isInitialLoading = eventsQuery.isPending && !eventsQuery.data;

  function navigateToSearchParams(params: URLSearchParams, options: { replace?: boolean } = {}) {
    const search = params.toString();
    navigate(
      {
        pathname: location.pathname,
        search: search ? `?${search}` : "",
        hash: location.hash
      },
      { replace: options.replace ?? false }
    );
  }

  function applyFilters(nextFilters: EventFilters, options: { replace?: boolean } = {}) {
    const normalized = normalizeEventFilters(nextFilters);
    if (eventFiltersEqual(filters, normalized)) {
      canonicalizeFilters(normalized);
      return;
    }
    navigateToSearchParams(eventFiltersToSearchParams(normalized, searchParams), options);
  }

  // Unchanged effective filters still replace the entry when owned keys need normalizing.
  function canonicalizeFilters(current: EventFilters) {
    if (!eventFilterParamsNeedNormalization(current, searchParams)) {
      return;
    }
    navigateToSearchParams(eventFiltersToSearchParams(current, searchParams), { replace: true });
  }

  function resetFilters() {
    const params = removeEventFilterParams(searchParams);
    // Removing owned keys replaces the entry unless the effective filters truly change.
    const replace = eventFiltersEqual(filters, parseEventFilterParams(params));
    if (replace && !hasEventFilterParams(searchParams)) {
      return;
    }
    navigateToSearchParams(params, { replace });
  }

  function hideEvent(eventId: string) {
    setHiddenEventIdList((current) =>
      current.includes(eventId) ? current : [...current, eventId]
    );
  }

  function showEvent(eventId: string) {
    setHiddenEventIdList((current) =>
      current.filter((currentEventId) => currentEventId !== eventId)
    );
  }

  return (
    <main className={classes.appShell}>
      <Container size="xl" px="lg" py="lg">
        <Stack gap="md">
          <EventHeader
            hasLoadedData={hasLoadedData}
            isFetching={eventsQuery.isFetching}
            showHidden={showHidden}
            visibleEventCount={visibleEventCount}
            onRefresh={() => {
              void eventsQuery.refetch();
            }}
            onShowHiddenChange={setShowHidden}
          />

          <EventFiltersForm
            categories={categories}
            filters={filters}
            onCategoriesChange={(selected) => applyFilters({ ...filters, categories: selected })}
            onScoreChange={(minScore) => applyFilters({ ...filters, minScore })}
            onQueryChange={(query) => applyFilters({ ...filters, query }, { replace: true })}
            onDateFromChange={(value) => {
              const dateFrom = coercePickerDate(value) ?? todayMorning();
              applyFilters({ ...filters, dateFrom, dateTo: defaultDateTo(dateFrom) });
            }}
            onDateToChange={(value) => {
              const dateTo = coercePickerDate(value) ?? defaultDateTo(filters.dateFrom);
              applyFilters({ ...filters, dateTo });
            }}
            onReset={resetFilters}
          />

          {isInitialLoading && (
            <Group justify="center" py="xl">
              <Loader color="amber" />
            </Group>
          )}

          {eventsQuery.isError && (
            <Alert color="red" variant="light">
              {errorMessage}
            </Alert>
          )}

          {hasLoadedData && days.length === 0 && (
            <Paper withBorder p="xl" bg="amber.0">
              <Text fw={600}>No events match these filters.</Text>
            </Paper>
          )}

          {hasLoadedData && days.length > 0 && (
            <>
              <VirtualEventList
                key={listRevision}
                items={listItems}
                hiddenEventIds={hiddenEventIds}
                onHideEvent={hideEvent}
                onShowEvent={showEvent}
              />
              <Group justify="center">
                <Button
                  variant="light"
                  onClick={() =>
                    applyFilters({ ...filters, dateTo: defaultDateTo(filters.dateTo ?? filters.dateFrom) })
                  }
                >
                  Next month
                </Button>
              </Group>
            </>
          )}
        </Stack>
      </Container>
    </main>
  );
}

function coercePickerDate(value: Date | string | null): Date | null {
  if (value instanceof Date) {
    return value;
  }
  if (typeof value === "string" && value) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
}
