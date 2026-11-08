import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Container,
  Divider,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
  Tooltip
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Info, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

import {
  fetchStats,
  statsQueryKey,
  type StatsCity,
  type StatsIngestionWeek,
  type StatsRecordMetrics,
  type StatsRefinementItemCounts,
  type StatsRefinementMetrics,
  type StatsResponse,
  type StatsSource,
  type StatsSourceSync
} from "../api";
import { formatInTimeZone } from "../timezone";

const STATUS_WEEKS = 8;
const NUMBER_FORMAT = new Intl.NumberFormat("en-LT");

const REFINEMENT_KINDS: ReadonlyArray<[keyof StatsRefinementItemCounts, string]> = [
  ["event", "Event"],
  ["advertisement", "Advertisement"],
  ["announcement", "Announcement"],
  ["non_event", "Non-event"],
  ["unknown", "Unknown"]
];

export function StatusRoute() {
  const statsQuery = useQuery({
    queryKey: statsQueryKey(STATUS_WEEKS),
    queryFn: ({ signal }) => fetchStats(STATUS_WEEKS, { signal })
  });

  const data = statsQuery.data;
  const isInitialLoading = statsQuery.isPending && !data;
  const isBackgroundRefresh = statsQuery.isFetching && Boolean(data);
  const errorMessage = statsQuery.error instanceof Error
    ? statsQuery.error.message
    : "Could not load data status";
  const refreshedAt = statsQuery.dataUpdatedAt
    ? new Date(statsQuery.dataUpdatedAt).toISOString()
    : null;
  const isEmpty = Boolean(
    data && data.sources.length === 0 && data.totals.ingestion.records_total === 0
  );

  function refetchStats() {
    void statsQuery.refetch();
  }

  return (
    <main>
      <Container size="lg" px="md" py="xl">
        <Stack gap="xl" data-testid="status-page">
          <Stack gap="xs">
            <Group justify="space-between" align="flex-start" gap="md" wrap="wrap">
              <div>
                <Title order={1}>Data status</Title>
                <Text size="sm" c="dimmed">
                  Stored ingestion, refinement, and recorded source sync.
                </Text>
              </div>
              <Group gap="sm">
                <Anchor component={Link} to="/vilnius" size="sm">
                  Browse Vilnius events
                </Anchor>
                <Button
                  variant="light"
                  leftSection={<RefreshCw size={16} />}
                  loading={statsQuery.isFetching}
                  onClick={refetchStats}
                >
                  Refresh
                </Button>
              </Group>
            </Group>

            {data && (
              <Group gap="xs" wrap="wrap">
                <Text size="sm" c="dimmed">
                  As of{" "}
                  <Text component="span" fw={600} c="dark.8">
                    {formatTimestamp(data.as_of, data.reporting_timezone)}
                  </Text>
                  {" · "}Reporting timezone:{" "}
                  <Text component="span" fw={600} c="dark.8">
                    {data.reporting_timezone}
                  </Text>
                </Text>
                {isBackgroundRefresh && (
                  <Badge variant="light" color="amber" aria-live="polite">
                    Refreshing
                  </Badge>
                )}
              </Group>
            )}
          </Stack>

          {isInitialLoading && (
            <Group justify="center" py="xl" gap="sm" aria-live="polite" data-testid="status-loading">
              <Loader color="amber" />
              <Text c="dimmed">Loading data status…</Text>
            </Group>
          )}

          {statsQuery.isError && !data && (
            <Alert
              color="red"
              variant="light"
              title="Data status unavailable"
              data-testid="status-error"
            >
              <Stack gap="sm" align="flex-start">
                <Text>{errorMessage}</Text>
                <Button variant="light" loading={statsQuery.isFetching} onClick={refetchStats}>
                  Retry
                </Button>
              </Stack>
            </Alert>
          )}

          {statsQuery.isError && data && (
            <Alert
              color="red"
              variant="light"
              title="Could not refresh data status"
              data-testid="status-refresh-error"
            >
              <Stack gap="sm" align="flex-start">
                <Text>{errorMessage}</Text>
                <Text size="sm">
                  Showing the last successfully loaded report
                  {refreshedAt
                    ? ` from ${formatTimestamp(refreshedAt, data.reporting_timezone)}`
                    : ""}
                  .
                </Text>
                <Button variant="light" loading={statsQuery.isFetching} onClick={refetchStats}>
                  Retry refresh
                </Button>
              </Stack>
            </Alert>
          )}

          {data && (
            <>
              {isEmpty && (
                <Alert
                  color="amber"
                  variant="light"
                  title="No stored records yet"
                  data-testid="status-empty"
                >
                  <Text size="sm">
                    Tables show zero counts and the published city registry.
                  </Text>
                </Alert>
              )}

              <Tabs defaultValue="ingestion" variant="outline" keepMounted={false}>
                <Tabs.List>
                  <Tabs.Tab value="ingestion">Ingestion</Tabs.Tab>
                  <Tabs.Tab value="refinement">Refinement</Tabs.Tab>
                  <Tabs.Tab value="sync">Sync</Tabs.Tab>
                  <Tabs.Tab value="cities">Cities</Tabs.Tab>
                </Tabs.List>

                <Tabs.Panel value="ingestion" pt="md">
                  <Stack gap="xl">
                    <IngestionSection
                      totals={data.totals.ingestion}
                      sources={data.sources}
                      timeZone={data.reporting_timezone}
                    />
                    <WeeklyCoverageSection weeks={data.weeks} sources={data.sources} />
                  </Stack>
                </Tabs.Panel>

                <Tabs.Panel value="refinement" pt="md">
                  <RefinementSection
                    totals={data.totals.refinement}
                    sources={data.sources}
                    timeZone={data.reporting_timezone}
                  />
                </Tabs.Panel>

                <Tabs.Panel value="sync" pt="md">
                  <SourceSyncSection
                    sources={data.sources}
                    timeZone={data.reporting_timezone}
                  />
                </Tabs.Panel>

                <Tabs.Panel value="cities" pt="md">
                  <CitySection data={data} />
                </Tabs.Panel>
              </Tabs>
            </>
          )}
        </Stack>
      </Container>
    </main>
  );
}

function InfoTip({ label, ariaLabel }: { label: string; ariaLabel: string }) {
  return (
    <Tooltip label={label} withArrow multiline w={280} events={{ hover: true, focus: true, touch: true }}>
      <ActionIcon variant="subtle" color="gray" size="sm" aria-label={ariaLabel}>
        <Info size={16} />
      </ActionIcon>
    </Tooltip>
  );
}

function IngestionSection({
  totals,
  sources,
  timeZone
}: {
  totals: StatsRecordMetrics;
  sources: StatsSource[];
  timeZone: string;
}) {
  return (
    <Stack gap="md" component="section" aria-label="Ingestion totals">
      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
        <MetricCard
          label="Raw records"
          value={formatCount(totals.records_total)}
          note="All stored raw records."
        />
        <MetricCard
          label="Pending refinement"
          value={formatCount(totals.pending_records_total)}
          note="Awaiting refinement; excludes ignored."
        />
        <MetricCard
          label="Ignored"
          value={formatCount(totals.ignored_records_total)}
          note="Expected failures excluded from refinement retries."
        />
        <MetricCard
          label="Oldest pending capture"
          value={formatTimestamp(totals.oldest_pending_captured_at, timeZone)}
          note="Original capture time, not queue wait."
          valueSize="lg"
        />
        <MetricCard
          label="Latest capture"
          value={formatTimestamp(totals.latest_captured_at, timeZone)}
          note="Most recent recorded capture."
          valueSize="lg"
        />
      </SimpleGrid>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={720}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="All-time raw records by source"
        >
          <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">Source</Table.Th>
                <Table.Th scope="col">Raw records</Table.Th>
                <Table.Th scope="col">Pending</Table.Th>
                <Table.Th scope="col">Ignored</Table.Th>
                <Table.Th scope="col">Latest capture</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sources.map((source) => (
                <Table.Tr key={source.source}>
                  <Table.Th scope="row">{source.source}</Table.Th>
                  <Table.Td>{formatCount(source.ingestion.records_total)}</Table.Td>
                  <Table.Td>{formatCount(source.ingestion.pending_records_total)}</Table.Td>
                  <Table.Td>{formatCount(source.ingestion.ignored_records_total)}</Table.Td>
                  <Table.Td>
                    {formatTimestamp(source.ingestion.latest_captured_at, timeZone)}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
            <Table.Tfoot bg="gray.0">
              <Table.Tr fw={700}>
                <Table.Th scope="row" fw={700}>All observed sources</Table.Th>
                <Table.Td fw={700}>{formatCount(totals.records_total)}</Table.Td>
                <Table.Td fw={700}>{formatCount(totals.pending_records_total)}</Table.Td>
                <Table.Td fw={700}>{formatCount(totals.ignored_records_total)}</Table.Td>
                <Table.Td fw={700}>{formatTimestamp(totals.latest_captured_at, timeZone)}</Table.Td>
              </Table.Tr>
            </Table.Tfoot>
          </Table>
        </Table.ScrollContainer>
      </Paper>
    </Stack>
  );
}

function MetricCard({
  label,
  value,
  note,
  valueSize = "xl"
}: {
  label: string;
  value: string;
  note: string;
  valueSize?: string;
}) {
  return (
    <Card withBorder padding="md" bg="white" component="article">
      <Text size="xs" tt="uppercase" fw={700} c="dimmed">
        {label}
      </Text>
      <Text fz={valueSize} fw={700} mt="xs" c="dark.8">
        {value}
      </Text>
      <Text size="xs" c="dimmed" mt="xs">
        {note}
      </Text>
    </Card>
  );
}

function WeeklyCoverageSection({
  weeks,
  sources
}: {
  weeks: StatsIngestionWeek[];
  sources: StatsSource[];
}) {
  return (
    <Stack gap="md" component="section" aria-label="Weekly captured records">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Group gap="xs" align="center">
          <Title order={2} size="h5">
            Weekly captured records
          </Title>
          <InfoTip
            ariaLabel="About capture time"
            label="Ingestion time is recorded as first capture. Imported or static records may carry historical capture times; duplicate fetches do not count again."
          />
        </Group>
        <Badge variant="light" color="wood">
          {weeks.length} weeks
        </Badge>
      </Group>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={1120}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="Weekly first-captured records by source"
        >
          <Table
            striped
            highlightOnHover
            withColumnBorders
            verticalSpacing="xs"
            horizontalSpacing="sm"
            tabularNums
          >
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">Source</Table.Th>
                {weeks.map((week) => (
                  <Table.Th key={week.week_start} scope="col">
                    <Text size="xs" fw={700}>
                      Week of {week.week_start}
                    </Text>
                    <Text size="xs" c="dimmed" fw={400}>
                      Ends {week.week_end}
                    </Text>
                    {week.is_partial && (
                      <Badge size="xs" variant="light" color="amber" mt="xs">
                        Partial
                      </Badge>
                    )}
                  </Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sources.map((source) => (
                <Table.Tr key={source.source}>
                  <Table.Th scope="row">{source.source}</Table.Th>
                  {weeks.map((week) => (
                    <WeekCountCell key={week.week_start} count={weekCount(source, week)} />
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
            <Table.Tfoot bg="gray.0">
              <Table.Tr fw={700}>
                <Table.Th scope="row" fw={700}>All observed sources</Table.Th>
                {weeks.map((week) => (
                  <WeekCountCell key={week.week_start} count={week.records} emphasized />
                ))}
              </Table.Tr>
            </Table.Tfoot>
          </Table>
        </Table.ScrollContainer>
      </Paper>
    </Stack>
  );
}

function WeekCountCell({ count, emphasized = false }: { count: number; emphasized?: boolean }) {
  return (
    <Table.Td fw={emphasized ? 700 : count > 0 ? 600 : 400}>
      {formatCount(count)}
    </Table.Td>
  );
}

function RefinementSection({
  totals,
  sources,
  timeZone
}: {
  totals: StatsRefinementMetrics;
  sources: StatsSource[];
  timeZone: string;
}) {
  return (
    <Stack gap="md" component="section" aria-label="Refinement output">
      <Group gap="xs" align="center">
        <Title order={2} size="h5">
          Refinement output
        </Title>
        <InfoTip
          ariaLabel="About refinement items"
          label="Output items are not raw records. Event items are all time and not deduplicated across sources."
        />
      </Group>

      <Paper withBorder p="md" bg="white">
        <Stack gap="sm">
          <Group justify="space-between" align="center" gap="sm">
            <Text fw={600}>Current refinement items</Text>
            <Text fw={700}>{formatCount(totals.refinement_items_total)}</Text>
          </Group>

          <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
            {REFINEMENT_KINDS.map(([kind, label]) => (
              <div key={kind}>
                <Text size="xs" tt="uppercase" fw={700} c="dimmed">
                  {label}
                </Text>
                <Text fw={600}>{formatCount(totals.refinement_items_by_kind[kind])}</Text>
              </div>
            ))}
          </SimpleGrid>

          <Divider />

          <Group gap="xs" align="center">
            <Text fw={600}>Refined event items:</Text>
            <Text fw={700}>{formatCount(totals.event_items_total)}</Text>
            <Badge variant="light" color="wood" size="sm">
              All time
            </Badge>
          </Group>

          <Text size="sm">
            Latest refinement result:{" "}
            <Text component="span" fw={600}>
              {formatTimestamp(totals.last_refined_at, timeZone)}
            </Text>
          </Text>
        </Stack>
      </Paper>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={900}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="Refinement output items by source"
        >
          <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">Source</Table.Th>
                <Table.Th scope="col">Refined items</Table.Th>
                <Table.Th scope="col">Event</Table.Th>
                <Table.Th scope="col">Advertisement</Table.Th>
                <Table.Th scope="col">Announcement</Table.Th>
                <Table.Th scope="col">Non-event</Table.Th>
                <Table.Th scope="col">Unknown</Table.Th>
                <Table.Th scope="col">Latest refinement</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sources.map((source) => (
                <Table.Tr key={source.source}>
                  <Table.Th scope="row">{source.source}</Table.Th>
                  <Table.Td>{formatCount(source.refinement.refinement_items_total)}</Table.Td>
                  <Table.Td>{formatCount(source.refinement.refinement_items_by_kind.event)}</Table.Td>
                  <Table.Td>
                    {formatCount(source.refinement.refinement_items_by_kind.advertisement)}
                  </Table.Td>
                  <Table.Td>
                    {formatCount(source.refinement.refinement_items_by_kind.announcement)}
                  </Table.Td>
                  <Table.Td>
                    {formatCount(source.refinement.refinement_items_by_kind.non_event)}
                  </Table.Td>
                  <Table.Td>{formatCount(source.refinement.refinement_items_by_kind.unknown)}</Table.Td>
                  <Table.Td>{formatTimestamp(source.refinement.last_refined_at, timeZone)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
            <Table.Tfoot bg="gray.0">
              <Table.Tr fw={700}>
                <Table.Th scope="row" fw={700}>All observed sources</Table.Th>
                <Table.Td fw={700}>{formatCount(totals.refinement_items_total)}</Table.Td>
                <Table.Td fw={700}>{formatCount(totals.refinement_items_by_kind.event)}</Table.Td>
                <Table.Td fw={700}>
                  {formatCount(totals.refinement_items_by_kind.advertisement)}
                </Table.Td>
                <Table.Td fw={700}>
                  {formatCount(totals.refinement_items_by_kind.announcement)}
                </Table.Td>
                <Table.Td fw={700}>
                  {formatCount(totals.refinement_items_by_kind.non_event)}
                </Table.Td>
                <Table.Td fw={700}>{formatCount(totals.refinement_items_by_kind.unknown)}</Table.Td>
                <Table.Td fw={700}>{formatTimestamp(totals.last_refined_at, timeZone)}</Table.Td>
              </Table.Tr>
            </Table.Tfoot>
          </Table>
        </Table.ScrollContainer>
      </Paper>
    </Stack>
  );
}

const SYNC_STATE_LABELS: Record<StatsSourceSync["state"], string> = {
  unknown: "No sync recorded",
  unfinished: "Unfinished",
  success: "Success",
  failure: "Failure"
};

const SYNC_STATE_COLORS: Record<StatsSourceSync["state"], string> = {
  unknown: "gray",
  unfinished: "gray",
  success: "green",
  failure: "red"
};

function SourceSyncSection({
  sources,
  timeZone
}: {
  sources: StatsSource[];
  timeZone: string;
}) {
  return (
    <Stack gap="md" component="section" aria-label="Source sync">
      <Group gap="xs" align="center">
        <Title order={2} size="h5">
          Source sync
        </Title>
        <InfoTip
          ariaLabel="About sync status"
          label="Unknown and unfinished are not terminal outcomes. A successful sync does not mean refinement or media upload is complete."
        />
      </Group>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={860}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="Recorded source sync attempts and last successful completion"
        >
          <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">Source</Table.Th>
                <Table.Th scope="col">Last attempt</Table.Th>
                <Table.Th scope="col">Attempt counts</Table.Th>
                <Table.Th scope="col">Last successful sync</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sources.map((source) => (
                <SourceSyncRow key={source.source} source={source} timeZone={timeZone} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>
    </Stack>
  );
}

function SourceSyncRow({ source, timeZone }: { source: StatsSource; timeZone: string }) {
  const sync = source.sync;
  const attempt = sync.last_attempt;

  return (
    <Table.Tr>
      <Table.Th scope="row">{source.source}</Table.Th>
      <Table.Td>
        <Badge variant="light" color={SYNC_STATE_COLORS[sync.state]} size="sm">
          {syncStateLabel(sync)}
        </Badge>
        {attempt && (
          <Text size="sm" mt="xs">
            {formatTimestamp(attempt.started_at, timeZone)}
          </Text>
        )}
        {attempt?.state === "unfinished" && (
          <Text size="xs" c="dimmed">
            Completion not recorded
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {attempt ? (
          attempt.state === "unfinished" ? (
            <Text size="sm" c="dimmed">
              Not recorded
            </Text>
          ) : (
            <Text size="sm">
              Fetched {formatCount(attempt.fetched_count)} · Stored{" "}
              {formatCount(attempt.inserted_count)} · Dup{" "}
              {formatCount(attempt.duplicate_count)}
            </Text>
          )
        ) : (
          <Text size="sm" c="dimmed">
            Not recorded
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {sync.last_success ? (
          <>
            <Text size="sm">{formatTimestamp(sync.last_success.completed_at, timeZone)}</Text>
            <Text size="xs" c="dimmed">
              Fetched {formatCount(sync.last_success.fetched_count)} · Stored{" "}
              {formatCount(sync.last_success.inserted_count)} · Dup{" "}
              {formatCount(sync.last_success.duplicate_count)}
            </Text>
          </>
        ) : (
          <Text size="sm" c="dimmed">
            No successful sync recorded
          </Text>
        )}
      </Table.Td>
    </Table.Tr>
  );
}

function syncStateLabel(sync: StatsSourceSync): string {
  if (sync.state === "failure" && sync.last_attempt?.failure_stage) {
    return `${SYNC_STATE_LABELS.failure}: ${sync.last_attempt.failure_stage}`;
  }
  return SYNC_STATE_LABELS[sync.state];
}

function CitySection({ data }: { data: StatsResponse }) {
  const assignedTotal = data.cities.reduce(
    (total, city) => total + city.event_items_total,
    0
  );

  return (
    <Stack gap="md" component="section" aria-label="City event items">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Title order={2} size="h5">
          City event items
        </Title>
        <Badge variant="light" color="wood">
          Refined event items
        </Badge>
      </Group>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={520}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="Refined event items by city"
        >
          <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">City</Table.Th>
                <Table.Th scope="col">Event items</Table.Th>
                <Table.Th scope="col">Sources</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.cities.map((city) => (
                <CityRow key={city.city_id} city={city} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      <Group gap="xs" wrap="wrap">
        <Badge variant="light" color="gray">
          Published cities {formatCount(data.supported_cities_total)}
        </Badge>
        <Badge variant="light" color="gray">
          Assigned {formatCount(assignedTotal)}
        </Badge>
        <Badge variant="light" color="gray">
          Unassigned {formatCount(data.unassigned_city_event_items_total)}
        </Badge>
        <Badge variant="light" color="gray">
          Unsupported {formatCount(data.unsupported_city_event_items_total)}
        </Badge>
        <Badge variant="light" color="gray">
          Total {formatCount(data.totals.refinement.event_items_total)}
        </Badge>
      </Group>
    </Stack>
  );
}

function CityRow({ city }: { city: StatsCity }) {
  return (
    <Table.Tr>
      <Table.Th scope="row">
        <Anchor component={Link} to={`/${city.country_code}/${city.slug}`} fw={600}>
          {city.name}
        </Anchor>
      </Table.Th>
      <Table.Td>{formatCount(city.event_items_total)}</Table.Td>
      <Table.Td>{formatCount(city.sources_with_event_items)}</Table.Td>
    </Table.Tr>
  );
}

function weekCount(source: StatsSource, week: StatsIngestionWeek): number {
  return source.weeks.find((entry) => entry.week_start === week.week_start)?.records ?? 0;
}

function formatCount(value: number): string {
  return NUMBER_FORMAT.format(value);
}

function formatTimestamp(value: string | null, timeZone: string): string {
  if (!value) {
    return "None recorded";
  }
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) {
    return "Unknown timestamp";
  }
  return formatInTimeZone(
    instant,
    timeZone,
    {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    },
    "en-LT"
  );
}
