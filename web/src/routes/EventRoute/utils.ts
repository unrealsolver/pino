import type { EventFilters } from "../../api";
import {
  defaultDateTo,
  todayMorning,
  type EventDay,
  type EventOccurrence
} from "../../eventUtils";

export type VirtualListItem =
  | { key: string; type: "day"; day: EventDay }
  | { key: string; type: "event"; occurrence: EventOccurrence };

export function createDefaultEventFilters(): EventFilters {
  const dateFrom = todayMorning();
  return {
    categories: [],
    minScore: 0,
    query: "",
    dateFrom,
    dateTo: defaultDateTo(dateFrom)
  };
}

export function buildVirtualListItems(
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

export function buildListRevision(items: VirtualListItem[]): string {
  let hash = 0;
  for (const item of items) {
    for (let index = 0; index < item.key.length; index += 1) {
      hash = (hash * 31 + item.key.charCodeAt(index)) | 0;
    }
  }
  return `${items.length}:${hash}`;
}
