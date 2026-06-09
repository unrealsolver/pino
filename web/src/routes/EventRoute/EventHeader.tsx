import { ActionIcon, Checkbox, Group, Text, Title } from "@mantine/core";
import { CalendarClock, RefreshCw } from "lucide-react";

export function EventHeader({
  hasLoadedData,
  isFetching,
  showHidden,
  visibleEventCount,
  onRefresh,
  onShowHiddenChange
}: {
  hasLoadedData: boolean;
  isFetching: boolean;
  showHidden: boolean;
  visibleEventCount: number;
  onRefresh: () => void;
  onShowHiddenChange: (value: boolean) => void;
}) {
  return (
    <Group justify="space-between" align="center" gap="md" wrap="wrap">
      <Group gap="sm">
        <CalendarClock size={28} strokeWidth={1.8} />
        <div>
          <Title order={1} size="h2">
            Events
          </Title>
          <Text size="sm" c="dimmed">
            {hasLoadedData ? `${visibleEventCount} visible` : "Loading"}
            {isFetching && hasLoadedData ? " - refreshing" : ""}
          </Text>
        </div>
      </Group>
      <Group gap="sm">
        <Checkbox
          label="Show hidden"
          checked={showHidden}
          onChange={(event) => onShowHiddenChange(event.currentTarget.checked)}
        />
        <ActionIcon
          size="lg"
          variant="light"
          aria-label="Refresh events"
          loading={isFetching}
          onClick={onRefresh}
        >
          <RefreshCw size={18} />
        </ActionIcon>
      </Group>
    </Group>
  );
}
