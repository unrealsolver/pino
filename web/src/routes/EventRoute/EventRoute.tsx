import { Alert, Button, Container, Group, Loader, Paper, Stack, Text } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { eventQueryKey, fetchEvents, type City, type EventFilters } from "../../api";
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
import { pickerValueToInstant, type PickerValueResult } from "../../timezone";
import { EventFiltersForm } from "./EventFiltersForm";
import classes from "./EventRoute.module.css";
import { EventHeader } from "./EventHeader";
import { VirtualEventList } from "./VirtualEventList";
import { buildListRevision, buildVirtualListItems } from "./utils";

type DateFieldErrors = { from?: string; to?: string };

export function EventRoute({ city }: { city: City }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const timeZone = city.timezone;
  // The URL is the single authoritative filter state; controls read it directly.
  const filters = useMemo(
    () => parseEventFilterParams(searchParams, new Date(), timeZone),
    [searchParams, location.key, timeZone]
  );
  const [dateErrors, setDateErrors] = useState<DateFieldErrors>({});

  useEffect(() => {
    setDateErrors({});
  }, [location.key]);

  const [hiddenEventIdList, setHiddenEventIdList] = useLocalStorage<string[]>({
    key: "pino-web-hidden-event-ids",
    defaultValue: []
  });
  const [showHidden, setShowHidden] = useLocalStorage({
    key: "pino-web-show-hidden-events",
    defaultValue: false
  });
  const eventsQuery = useQuery({
    queryKey: eventQueryKey(city.id, filters),
    queryFn: ({ signal }) => fetchEvents(city.id, filters, { signal }),
    // Only keep previous results for filter edits in the same city; switching
    // cities must never show the previous city's placeholder events.
    placeholderData: (previousData, previousQuery) =>
      previousQuery?.queryKey[1] === city.id ? previousData : undefined
  });

  const categories = eventsQuery.data?.categories ?? [];
  const calendarWindowEnd = useMemo(
    () => filters.dateTo ?? defaultDateTo(filters.dateFrom, timeZone),
    [filters.dateFrom, filters.dateTo, timeZone]
  );
  const days = useMemo(
    () =>
      groupEventsByDay(
        eventsQuery.data?.events ?? [],
        filters.dateFrom,
        calendarWindowEnd,
        timeZone
      ),
    [calendarWindowEnd, eventsQuery.data?.events, filters.dateFrom, timeZone]
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
    const normalized = normalizeEventFilters(nextFilters, timeZone);
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
    setDateErrors({});
    const params = removeEventFilterParams(searchParams);
    // Removing owned keys replaces the entry unless the effective filters truly change.
    const replace = eventFiltersEqual(
      filters,
      parseEventFilterParams(params, new Date(), timeZone)
    );
    if (replace && !hasEventFilterParams(searchParams)) {
      return;
    }
    navigateToSearchParams(params, { replace });
  }

  function dateErrorMessage(result: PickerValueResult): string | null {
    if (result.error === "nonexistent") {
      return `That time does not exist in ${city.name} on that date. Choose another time.`;
    }
    if (result.error === "invalid") {
      return "Choose a valid date and time.";
    }
    return null;
  }

  function changeDateFrom(value: Date | string | null) {
    const result = pickerValueToInstant(value, filters.dateFrom, timeZone);
    const error = dateErrorMessage(result);
    setDateErrors((current) => ({ ...current, from: error ?? undefined }));
    if (error || !result.instant) {
      if (!result.instant && !error) {
        const dateFrom = todayMorning(undefined, timeZone);
        applyFilters({ ...filters, dateFrom, dateTo: defaultDateTo(dateFrom, timeZone) });
      }
      return;
    }
    // Re-emitting the unchanged displayed wall time is a true no-op, so it must
    // not reset a separately edited To value.
    if (result.instant.getTime() === filters.dateFrom.getTime()) {
      canonicalizeFilters(filters);
      return;
    }
    applyFilters({
      ...filters,
      dateFrom: result.instant,
      dateTo: defaultDateTo(result.instant, timeZone)
    });
  }

  function changeDateTo(value: Date | string | null) {
    const result = pickerValueToInstant(value, filters.dateTo, timeZone);
    const error = dateErrorMessage(result);
    setDateErrors((current) => ({ ...current, to: error ?? undefined }));
    if (error) {
      return;
    }
    const dateTo = result.instant ?? defaultDateTo(filters.dateFrom, timeZone);
    if (filters.dateTo && dateTo.getTime() === filters.dateTo.getTime()) {
      canonicalizeFilters(filters);
      return;
    }
    applyFilters({ ...filters, dateTo });
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
            cityName={city.name}
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
            timeZone={timeZone}
            dateFromError={dateErrors.from}
            dateToError={dateErrors.to}
            onCategoriesChange={(selected) => applyFilters({ ...filters, categories: selected })}
            onScoreChange={(minScore) => applyFilters({ ...filters, minScore })}
            onQueryChange={(query) => applyFilters({ ...filters, query }, { replace: true })}
            onDateFromChange={changeDateFrom}
            onDateToChange={changeDateTo}
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
                timeZone={timeZone}
                hiddenEventIds={hiddenEventIds}
                onHideEvent={hideEvent}
                onShowEvent={showEvent}
              />
              <Group justify="center">
                <Button
                  variant="light"
                  onClick={() =>
                    applyFilters({
                      ...filters,
                      dateTo: defaultDateTo(filters.dateTo ?? filters.dateFrom, timeZone)
                    })
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
