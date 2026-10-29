import { ActionIcon, Anchor, Checkbox, Group, Text, Title } from "@mantine/core";
import { CalendarClock, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

export function EventHeader({
  cityName,
  hasLoadedData,
  isFetching,
  showHidden,
  visibleEventCount,
  onRefresh,
  onShowHiddenChange
}: {
  cityName: string;
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
            Events in {cityName}
          </Title>
          <Text size="sm" c="dimmed">
            {hasLoadedData ? `${visibleEventCount} visible` : "Loading"}
            {isFetching && hasLoadedData ? " - refreshing" : ""}
          </Text>
        </div>
      </Group>
      <Group gap="sm">
        <Anchor component={Link} to="/status" size="sm">
          Data status
        </Anchor>
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
