import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Checkbox,
  Container,
  Group,
  Loader,
  MultiSelect,
  NumberInput,
  Paper,
  Stack,
  Text,
  TextInput,
  Tooltip,
  Title
} from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { useLocalStorage } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { CalendarClock, ExternalLink, Eye, EyeOff, RefreshCw, Search } from "lucide-react";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

import { eventQueryKey, fetchEvents, type EventFilters, type EventItem } from "../api";
import {
  defaultDateTo,
  formatEventOverflow,
  formatTimeRange,
  groupEventsByDay,
  todayMorning,
  topCategories,
  type EventDay,
  type EventOccurrence
} from "../eventUtils";

type VirtualListItem =
  | { key: string; type: "day"; day: EventDay }
  | { key: string; type: "event"; occurrence: EventOccurrence };

export function EventRoute() {
  const [filters, setFilters] = useState<EventFilters>(() => {
    const dateFrom = todayMorning();
    return {
      categories: [],
      minScore: 0,
      query: "",
      dateFrom,
      dateTo: defaultDateTo(dateFrom)
    };
  });
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
    eventsQuery.data?.events.filter((event) => !hiddenEventIds.has(event.id)) ?? []
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
    setHiddenEventIdList((current) => current.filter((currentEventId) => currentEventId !== eventId));
  }

  return (
    <main className="appShell">
      <Container size="xl" px="lg" py="lg">
        <Stack gap="md">
          <Group justify="space-between" align="center" gap="md" wrap="wrap">
            <Group gap="sm">
              <CalendarClock size={28} strokeWidth={1.8} />
              <div>
                <Title order={1} size="h2">
                  Events
                </Title>
                <Text size="sm" c="dimmed">
                  {hasLoadedData ? `${visibleEventCount} visible` : "Loading"}
                  {eventsQuery.isFetching && hasLoadedData ? " - refreshing" : ""}
                </Text>
              </div>
            </Group>
            <Group gap="sm">
              <Checkbox
                label="Show hidden"
                checked={showHidden}
                onChange={(event) => setShowHidden(event.currentTarget.checked)}
              />
              <ActionIcon
                size="lg"
                variant="light"
                aria-label="Refresh events"
                loading={eventsQuery.isFetching}
                onClick={() => {
                  void eventsQuery.refetch();
                }}
              >
                <RefreshCw size={18} />
              </ActionIcon>
            </Group>
          </Group>

          <Paper withBorder p="sm" bg="amber.0">
            <Group align="end" gap="sm" wrap="wrap">
              <MultiSelect
                className="filterControl filterWide"
                label="Tags"
                placeholder="Any category"
                data={categories}
                value={filters.categories}
                onChange={(categories) => setFilters((current) => ({ ...current, categories }))}
                searchable
                clearable
                comboboxProps={{ withinPortal: false }}
              />
              <NumberInput
                className="filterControl filterScore"
                label="Score"
                min={0}
                max={1}
                step={0.1}
                decimalScale={2}
                value={filters.minScore}
                onChange={(value) =>
                  setFilters((current) => ({
                    ...current,
                    minScore: typeof value === "number" ? value : 0
                  }))
                }
              />
              <TextInput
                className="filterControl filterWide"
                label="Text"
                placeholder="Search title, summary, text"
                leftSection={<Search size={16} />}
                value={filters.query}
                onChange={(event) =>
                  setFilters((current) => ({ ...current, query: event.currentTarget.value }))
                }
              />
              <DateTimePicker
                className="filterControl filterDate"
                label="From"
                valueFormat="YYYY-MM-DD HH:mm"
                value={filters.dateFrom}
                onChange={(value) => {
                  const dateFrom = coercePickerDate(value) ?? todayMorning();
                  setFilters((current) => ({
                    ...current,
                    dateFrom,
                    dateTo: defaultDateTo(dateFrom)
                  }));
                }}
              />
              <DateTimePicker
                className="filterControl filterDate"
                label="To"
                valueFormat="YYYY-MM-DD HH:mm"
                value={filters.dateTo}
                onChange={(value) =>
                  setFilters((current) => ({
                    ...current,
                    dateTo: coercePickerDate(value) ?? defaultDateTo(current.dateFrom)
                  }))
                }
              />
              <Button
                variant="light"
                onClick={() =>
                  setFilters(() => {
                    const dateFrom = todayMorning();
                    return {
                      categories: [],
                      minScore: 0,
                      query: "",
                      dateFrom,
                      dateTo: defaultDateTo(dateFrom)
                    };
                  })
                }
              >
                Reset
              </Button>
            </Group>
          </Paper>

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
                    setFilters((current) => ({
                      ...current,
                      dateTo: defaultDateTo(current.dateTo ?? current.dateFrom)
                    }))
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

function VirtualEventList({
  items,
  hiddenEventIds,
  onHideEvent,
  onShowEvent
}: {
  items: VirtualListItem[];
  hiddenEventIds: Set<string>;
  onHideEvent: (eventId: string) => void;
  onShowEvent: (eventId: string) => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [scrollMargin, setScrollMargin] = useState(0);
  const getVirtualItemKey = useCallback((index: number) => items[index]?.key ?? index, [items]);
  const updateScrollMargin = useCallback(() => {
    const nextScrollMargin = listRef.current?.offsetTop ?? 0;
    setScrollMargin((current) => (current === nextScrollMargin ? current : nextScrollMargin));
  }, []);

  useLayoutEffect(() => {
    updateScrollMargin();
  });

  useLayoutEffect(() => {
    window.addEventListener("resize", updateScrollMargin);
    return () => window.removeEventListener("resize", updateScrollMargin);
  }, [updateScrollMargin]);

  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: (index) => (items[index]?.type === "day" ? 40 : 82),
    getItemKey: getVirtualItemKey,
    overscan: 12,
    scrollMargin
  });

  return (
    <div ref={listRef} className="virtualList" style={{ height: virtualizer.getTotalSize() }}>
      {virtualizer.getVirtualItems().map((virtualRow) => {
        const item = items[virtualRow.index];
        if (!item) {
          return null;
        }
        return (
          <div
            key={virtualRow.key}
            className="virtualRow"
            data-index={virtualRow.index}
            ref={virtualizer.measureElement}
            style={{
              transform: `translateY(${virtualRow.start - virtualizer.options.scrollMargin}px)`
            }}
          >
            {item.type === "day" ? (
              <Paper className="dayHeader" withBorder p="xs" bg="wood.1" radius="sm">
                <Text component="h2" c="wood.9" size="sm" fw={700} m={0}>
                  {item.day.label}
                </Text>
                <HiddenDayControl occurrences={item.day.events} hiddenEventIds={hiddenEventIds} />
              </Paper>
            ) : (
              <EventLine
                occurrence={item.occurrence}
                isHidden={hiddenEventIds.has(item.occurrence.event.id)}
                onToggleHidden={() =>
                  hiddenEventIds.has(item.occurrence.event.id)
                    ? onShowEvent(item.occurrence.event.id)
                    : onHideEvent(item.occurrence.event.id)
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function coercePickerDate(value: Date | string | null): Date | null {
  if (value instanceof Date) {
    return value;
  }
  if (typeof value === "string" && value) {
    return new Date(value);
  }
  return null;
}

function buildVirtualListItems(
  days: EventDay[],
  hiddenEventIds: Set<string>,
  showHidden: boolean
): VirtualListItem[] {
  return days.flatMap((day) => [
    { key: `day:${day.key}`, type: "day" as const, day },
    ...day.events
      .filter((occurrence) => showHidden || !hiddenEventIds.has(occurrence.event.id))
      .map((occurrence) => ({
        key: `event:${occurrence.key}`,
        type: "event" as const,
        occurrence
      }))
  ]);
}

function buildListRevision(items: VirtualListItem[]): string {
  let hash = 0;
  for (const item of items) {
    for (let index = 0; index < item.key.length; index += 1) {
      hash = (hash * 31 + item.key.charCodeAt(index)) | 0;
    }
  }
  return `${items.length}:${hash}`;
}

function HiddenDayControl({
  occurrences,
  hiddenEventIds
}: {
  occurrences: EventOccurrence[];
  hiddenEventIds: Set<string>;
}) {
  const hiddenIds = new Set(
    occurrences
      .map((occurrence) => occurrence.event.id)
      .filter((eventId) => hiddenEventIds.has(eventId))
  );
  if (hiddenIds.size === 0) {
    return null;
  }
  return (
    <Text className="hiddenDayText" size="xs" c="wood.7">
      {hiddenIds.size} hidden
    </Text>
  );
}

function EventLine({
  occurrence,
  isHidden,
  onToggleHidden
}: {
  occurrence: EventOccurrence;
  isHidden: boolean;
  onToggleHidden: () => void;
}) {
  const event = occurrence.event;
  const categories = topCategories(event);
  const overflow = formatEventOverflow(event);
  return (
    <Paper
      className="eventLine"
      component="article"
      withBorder
      p="sm"
      bg={isHidden ? "wood.0" : "amber.0"}
      opacity={isHidden ? 0.56 : 1}
    >
      <div className="eventTime">
        <Text fw={600} c="amber.9">
          {formatTimeRange(event, occurrence.day)}
        </Text>
        {overflow && (
          <Text className="eventOverflow" size="xs" c="wood.7">
            {overflow}
          </Text>
        )}
      </div>
      <div className="eventMain">
        <Group gap="xs" wrap="nowrap">
          <Text className="eventTitle" fw={600}>
            {event.title}
          </Text>
          {event.url && (
            <ActionIcon
              component="a"
              href={event.url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${event.title}`}
              size="sm"
              variant="subtle"
            >
              <ExternalLink size={14} />
            </ActionIcon>
          )}
        </Group>
        {event.summary && (
          <Text size="sm" c="dimmed" lineClamp={2}>
            {event.summary}
          </Text>
        )}
      </div>
      <Group className="eventTags" gap={6} wrap="wrap">
        {categories.map((category) => (
          <Badge key={category} size="sm" variant="light" color="wood">
            {category}
          </Badge>
        ))}
      </Group>
      <Tooltip label={isHidden ? "Show event" : "Hide event"} withArrow>
        <ActionIcon
          className="eventHide"
          size="sm"
          variant="subtle"
          color="wood"
          aria-label={isHidden ? "Show event" : "Hide event"}
          onClick={onToggleHidden}
        >
          {isHidden ? <Eye size={15} /> : <EyeOff size={15} />}
        </ActionIcon>
      </Tooltip>
    </Paper>
  );
}
