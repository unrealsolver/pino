import { ActionIcon, Badge, Group, Image, Paper, Progress, Stack, Text, ThemeIcon, Tooltip } from "@mantine/core";
import classes from "./EventLine.module.css";
import { ExternalLink, Eye, EyeOff, MapPin } from "lucide-react";

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
  const cover = (
    <Image
      src={event.images?.[0]}
      fallbackSrc="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='100'/%3E"
      alt=""
      loading="lazy"
      w={80}
      h={100}
      radius="sm"
      bg="wood.1"
    />
  );
  return (
    <Paper
      className={classes.eventLine}
      component="article"
      withBorder
      p="sm"
      bg={isHidden ? "wood.0" : "amber.0"}
      opacity={isHidden ? 0.56 : 1}
    >
      <div className={classes.eventTime}>
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
      <div className={classes.eventMain}>
        {event.images?.[0] ? (
          <a href={event.images[0]} target="_blank" rel="noreferrer" aria-label={`View cover for ${event.title}`}>
            {cover}
          </a>
        ) : cover}
        <Stack gap={0} miw={0} mih={100}>
          <Group gap="xs" wrap="nowrap" align="start">
            <Text className={classes.breakAnywhere} miw={0} fw={600} lineClamp={2} title={event.title}>
              {event.summary}
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
            <Text textWrap="nowrap" size="xs" c="wood.7">{event.source}</Text>
          </Group>
          {event.title && (
            <Text size="sm" c="dimmed" lineClamp={2}>
              {event.title}
            </Text>
          )}
          {event.location && (
            <Group gap="0">
              <ThemeIcon variant="subtle" size="sm" ml="-6">
                <MapPin size={14} />
              </ThemeIcon>
              <Text size="sm" c="dimmed">{event.location}</Text>
            </Group>
          )}
          <Text className={classes.breakAnywhere} mt="auto" pt="xs" size="xs" c="wood.6">
            ID{" "}
            <Text component="span" inherit c="wood.7" className={classes.selectableId}>
              {event.refinement_id}
            </Text>
          </Text>
        </Stack>
      </div>
      <Group className={classes.eventTags} gap={6} wrap="wrap">
        {categories.map((category) => (
          <Badge key={category} size="sm" variant="light" color="wood">
            {category}
          </Badge>
        ))}
      </Group>
      <Tooltip label={isHidden ? "Show event" : "Hide event"} withArrow>
        <ActionIcon
          className={classes.eventHide}
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
