import { Alert, Button, Container, Group, Loader, Paper, Stack, Text } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useLocalStorage } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { eventQueryKey, fetchEvents, type EventFilters } from "../../api";
import { defaultDateTo, groupEventsByDay } from "../../eventUtils";
import { EventFiltersForm } from "./EventFiltersForm";
import classes from "./EventRoute.module.css";
import { EventHeader } from "./EventHeader";
import { VirtualEventList } from "./VirtualEventList";
import { buildListRevision, buildVirtualListItems, createDefaultEventFilters } from "./utils";

export function EventRoute() {
  const initialFilters = useMemo(createDefaultEventFilters, []);
  const filterForm = useForm<EventFilters>({
    initialValues: initialFilters
  });
  const filters = filterForm.values;
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

          <EventFiltersForm categories={categories} form={filterForm} />

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
                    filterForm.setFieldValue(
                      "dateTo",
                      defaultDateTo(filterForm.values.dateTo ?? filterForm.values.dateFrom)
                    )
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
