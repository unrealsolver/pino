import {
  Alert, Anchor, Badge, Button, Code, Container, Group, Image, Loader, Paper,
  SimpleGrid, Stack, Text, Title
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { fetchEvent } from "../api";
import { formatInTimeZone } from "../timezone";

type EventNavigation = {
  listPath: string;
  startsAt: string;
  endsAt: string | null;
  timeZone: string;
};

export function EventDetailRoute() {
  const { refinementId = "" } = useParams();
  const navigation = useLocation().state as EventNavigation | null;
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [refinementId]);

  const query = useQuery({
    queryKey: ["event", refinementId],
    queryFn: ({ signal }) => fetchEvent(refinementId, { signal })
  });
  const event = query.data;
  const cityPath = event?.city_id && /^[a-z]{2}\/[a-z0-9-]+$/.test(event.city_id)
    ? `/${event.city_id}`
    : "/vilnius";
  const sourceUrl = event?.url && /^https?:\/\//i.test(event.url) ? event.url : null;

  return (
    <Container component="main" size="md" py="xl">
      <Stack gap="lg">
        <Anchor component={Link} to={navigation?.listPath ?? cityPath} w="fit-content">
          {navigation ? "Back to events" : "Browse events"}
        </Anchor>
        {query.isPending && <Loader aria-label="Loading event" />}
        {query.isError && (
          <Alert color="red" title="Could not load event">
            <Stack align="start">
              <Text>{query.error.message}</Text>
              <Button onClick={() => void query.refetch()}>Retry</Button>
            </Stack>
          </Alert>
        )}
        {event === null && <Title order={1}>Event not found</Title>}
        {event && (
          <>
            <Stack gap="xs">
              <Title order={1}>{event.title}</Title>
              {event.location && <Text>{event.location}</Text>}
              {navigation && (
                <Text fw={600}>
                  {formatDate(navigation.startsAt, navigation.timeZone)}
                  {navigation.endsAt && ` – ${formatDate(navigation.endsAt, navigation.timeZone)}`}
                  {" · "}{navigation.timeZone}
                </Text>
              )}
              <Group gap="sm">
                <Text size="sm" c="dimmed">{event.source}</Text>
                {sourceUrl && (
                  <Anchor href={sourceUrl} target="_blank" rel="noreferrer">
                    Open original listing
                  </Anchor>
                )}
              </Group>
            </Stack>

            {event.images.length > 0 && (
              <SimpleGrid cols={{ base: 1, sm: event.images.length > 1 ? 2 : 1 }}>
                {event.images.map((src, index) => (
                  <Image
                    key={`${index}:${src}`}
                    src={src}
                    alt={`Event image ${index + 1}`}
                    fit="contain"
                    mah="70vh"
                    radius="md"
                    loading={index === 0 ? "eager" : "lazy"}
                  />
                ))}
              </SimpleGrid>
            )}

            {(event.text || (event.source_title && event.source_title !== event.title)) && (
              <Paper withBorder p="md">
                <Stack gap="xs">
                  <Title order={2} size="h4">Original listing</Title>
                  {event.source_title && event.source_title !== event.title && (
                    <Text fw={600}>{event.source_title}</Text>
                  )}
                  {event.text && <Text style={{ whiteSpace: "pre-wrap" }}>{event.text}</Text>}
                </Stack>
              </Paper>
            )}

            <Paper withBorder p="md">
              <Stack gap="xs">
                <Title order={2} size="h4">Schedule</Title>
                <Text size="sm" c="dimmed">{event.timezone}</Text>
                <DetailField label="Relevant from" value={formatDate(event.relevant_from, event.timezone)} />
                <DetailField label="Relevant to" value={formatDate(event.relevant_to, event.timezone)} />
                {event.schedule && <Code block>{JSON.stringify(event.schedule, null, 2)}</Code>}
                {event.weekly_multirange && (
                  <Stack gap="xs">
                    <Text size="sm" fw={600}>Weekly index (int4multirange)</Text>
                    <Text size="xs" c="dimmed">Local minutes of the week, starting Monday at 00:00.</Text>
                    <Code block>{event.weekly_multirange}</Code>
                  </Stack>
                )}
              </Stack>
            </Paper>

            {Object.keys(event.category_scores).length > 0 && (
              <Stack gap="xs">
                <Title order={2} size="h4">Category scores</Title>
                <Group gap="xs">
                  {Object.entries(event.category_scores)
                    .sort(([, a], [, b]) => b - a)
                    .map(([name, score]) => (
                      <Badge key={name} color="wood" variant="light" tt="none">
                        {name} · {Math.round(score * 100)}%
                      </Badge>
                    ))}
                </Group>
              </Stack>
            )}

            <Paper withBorder p="md">
              <Stack gap="xs">
                <Title order={2} size="h4">Record details</Title>
                <DetailField label="City" value={event.city_id} />
                <DetailField label="Source kind" value={event.source_kind} />
                <DetailField label="Source event ID" value={event.source_event_id} />
                <DetailField label="Record ID" value={event.record_id} />
                <DetailField label="Refinement ID" value={event.refinement_id} />
                <DetailField label="Published" value={formatDate(event.published_at, event.timezone)} />
                <DetailField label="Captured" value={formatDate(event.captured_at, event.timezone)} />
                <DetailField label="Refined" value={formatDate(event.refined_at, event.timezone)} />
              </Stack>
            </Paper>
          </>
        )}
      </Stack>
    </Container>
  );
}

function DetailField({ label, value }: { label: string; value: string | null }) {
  return (
    <Text size="sm">
      <Text component="span" fw={600} inherit>{label}</Text>{" · "}{value ?? "—"}
    </Text>
  );
}

function formatDate(value: string | null, timeZone: string): string | null {
  return value ? formatInTimeZone(new Date(value), timeZone, {
    dateStyle: "medium",
    timeStyle: "short"
  }) : null;
}
