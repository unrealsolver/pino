import { Text } from "@mantine/core";

import type { EventOccurrence } from "../../eventUtils";

export function HiddenDayControl({
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
