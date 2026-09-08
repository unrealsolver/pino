import { ActionIcon, Badge, Group, Paper, Progress, Text, Tooltip } from "@mantine/core";
import { ExternalLink, Eye, EyeOff } from "lucide-react";

import {
  eventProgress,
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
  const progress = eventProgress(event, occurrence.day);
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
        {progress && (
          <Tooltip
            label={`${progress.range} · relative to this calendar day`}
            withArrow
            events={{ hover: true, focus: true, touch: true }}
          >
            <div tabIndex={0} aria-label={`${progress.label}, ${progress.range}`}>
              <Text size="xs" c="wood.7" mt={4} mb={4}>{progress.label}</Text>
              <Progress
                value={progress.value}
                size="xs"
                radius="xl"
                color="amber"
                aria-label="Event duration elapsed"
              />
            </div>
          </Tooltip>
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
        <Text size="xs" c="wood.6">
          ID{" "}
          <Text component="span" inherit c="wood.7" style={{ userSelect: "all" }}>
            {event.refinement_id}
          </Text>
        </Text>
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
