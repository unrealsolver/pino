import { ActionIcon, Badge, Group, Paper, Text, Tooltip } from "@mantine/core";
import { ExternalLink, Eye, EyeOff } from "lucide-react";

import {
  formatEventOverflow,
  formatTimeRange,
  topCategories,
  type EventOccurrence
} from "../../eventUtils";

export function EventLine({
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
