import {
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
  Text,
  Title
} from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
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
                  Stored ingestion, refinement, and recorded source sync. Read-only.
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
                  Report as of{" "}
                  <Text component="span" fw={600} c="dark.8">
                    {formatTimestamp(data.as_of, data.reporting_timezone)}
                  </Text>
                  . Reporting timezone:{" "}
                  <Text component="span" fw={600} c="dark.8">
                    {data.reporting_timezone}
                  </Text>
                  . Weeks start Monday.
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
                    No raw records are stored yet. The tables show zero counts, and the city
                    table lists the published registry.
                  </Text>
                </Alert>
              )}

              <IngestionSection
                totals={data.totals.ingestion}
                timeZone={data.reporting_timezone}
              />

              <WeeklyCoverageSection
                weeks={data.weeks}
                sources={data.sources}
                totals={data.totals.ingestion}
                timeZone={data.reporting_timezone}
              />

              <RefinementSection
                totals={data.totals.refinement}
                sources={data.sources}
                timeZone={data.reporting_timezone}
              />

              <SourceSyncSection sources={data.sources} />

              <CitySection data={data} />
            </>
          )}
        </Stack>
      </Container>
    </main>
  );
}

function IngestionSection({
  totals,
  timeZone
}: {
  totals: StatsRecordMetrics;
  timeZone: string;
}) {
  return (
    <Stack gap="md" component="section" aria-labelledby="status-ingestion-heading">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Title order={2} size="h4" id="status-ingestion-heading">
          Ingestion and coverage
        </Title>
        <Badge variant="light" color="amber">
          Raw record counts
        </Badge>
      </Group>

      <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }} spacing="md">
        <MetricCard
          label="Raw records"
          value={formatCount(totals.records_total)}
          note="All stored raw records, all time. Includes records without a refinement."
        />
        <MetricCard
          label="Records with refinement"
          value={formatCount(totals.records_with_refinement_total)}
          note="Distinct raw records with at least one current refinement result. Each record is counted once."
        />
        <MetricCard
          label="Pending refinement"
          value={formatCount(totals.pending_records_total)}
          note="Raw records with no current refinement result. Pending records do not indicate failed or running work."
        />
        <MetricCard
          label="Oldest pending capture"
          value={formatTimestamp(totals.oldest_pending_captured_at, timeZone)}
          note="Original capture time of the oldest pending record, not measured queue wait time."
          valueSize="lg"
        />
      </SimpleGrid>

      <Paper withBorder p="md" bg="white">
        <Text size="sm">
          Latest captured record:{" "}
          <Text component="span" fw={600}>
            {formatTimestamp(totals.latest_captured_at, timeZone)}
          </Text>
        </Text>
      </Paper>

      <Alert color="amber" variant="light" title="Ingestion time is recorded as first capture">
        <Stack gap="xs">
          <Text size="sm">
            “First captured records” are grouped by the original recorded capture time. That time
            is when a record was recorded, not when it was inserted into the database: imported or
            static records may carry a historical capture time, and a duplicate fetch does not
            count again.
          </Text>
          <Text size="sm">
            The oldest pending capture is measured from capture time, not queue wait. Pending
            records are not evidence of failed or running refinement jobs.
          </Text>
        </Stack>
      </Alert>
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
  sources,
  totals,
  timeZone
}: {
  weeks: StatsIngestionWeek[];
  sources: StatsSource[];
  totals: StatsRecordMetrics;
  timeZone: string;
}) {
  return (
    <Stack gap="md" component="section" aria-labelledby="status-weekly-heading">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Title order={2} size="h4" id="status-weekly-heading">
          Weekly ingestion by source
        </Title>
        <Badge variant="light" color="wood">
          {weeks.length} weeks
        </Badge>
      </Group>

      <Text size="sm" c="dimmed">
        “First captured records” groups raw records by their original recorded capture time
        into Monday-start weeks in {timeZone}. Refined and pending values are the current
        coverage of the records captured in that week, as of this report. They are not jobs
        completed during that week and not a historical queue size.
      </Text>

      <Paper withBorder p="md" bg="white">
        <Stack gap="sm">
          <Text fw={600}>All-time coverage and pending outside window by source</Text>
          <Table.ScrollContainer
            minWidth={760}
            type="native"
            role="region"
            tabIndex={0}
            aria-label="All-time ingestion coverage and pending outside window by source"
          >
            <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
              <Table.Caption>
                Raw record coverage by observed source. “Pending outside window” counts all
                pending captures outside the displayed capture interval, including future-dated
                captures. “Latest capture” is a storage timestamp, not a sync time.
              </Table.Caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Source</Table.Th>
                  <Table.Th scope="col">Raw records</Table.Th>
                  <Table.Th scope="col">With refinement</Table.Th>
                  <Table.Th scope="col">Pending</Table.Th>
                  <Table.Th scope="col">Pending outside window</Table.Th>
                  <Table.Th scope="col">Latest capture</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {sources.map((source) => (
                  <Table.Tr key={source.source}>
                    <Table.Th scope="row">{source.source}</Table.Th>
                    <Table.Td>{formatCount(source.ingestion.records_total)}</Table.Td>
                    <Table.Td>
                      {formatCount(source.ingestion.records_with_refinement_total)}
                    </Table.Td>
                    <Table.Td>{formatCount(source.ingestion.pending_records_total)}</Table.Td>
                    <Table.Td>
                      {formatCount(
                        pendingOutsideWindow(source.weeks, source.ingestion.pending_records_total)
                      )}
                    </Table.Td>
                    <Table.Td>
                      {formatTimestamp(source.ingestion.latest_captured_at, timeZone)}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
              <Table.Tfoot>
                <Table.Tr>
                  <Table.Th scope="row">All observed sources</Table.Th>
                  <Table.Td>{formatCount(totals.records_total)}</Table.Td>
                  <Table.Td>{formatCount(totals.records_with_refinement_total)}</Table.Td>
                  <Table.Td>{formatCount(totals.pending_records_total)}</Table.Td>
                  <Table.Td>
                    {formatCount(pendingOutsideWindow(weeks, totals.pending_records_total))}
                  </Table.Td>
                  <Table.Td>{formatTimestamp(totals.latest_captured_at, timeZone)}</Table.Td>
                </Table.Tr>
              </Table.Tfoot>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      </Paper>

      <Paper withBorder p="md" bg="white">
        <Stack gap="sm">
          <Text fw={600}>First captured records and current cohort coverage</Text>
          <Table.ScrollContainer
            minWidth={1120}
            type="native"
            role="region"
            tabIndex={0}
            aria-label="Eight-week first-captured records and current coverage by source"
          >
            <Table
              striped
              highlightOnHover
              withColumnBorders
              verticalSpacing="xs"
              horizontalSpacing="sm"
              tabularNums
            >
              <Table.Caption>
                Week bounds are Monday-start half-open local dates; the end date is exclusive.
                The current week is partial and marked. Coverage for an older cohort changes when
                an old record is refined later.
              </Table.Caption>
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
                        <>
                          <Badge size="xs" variant="light" color="amber" mt="xs">
                            Partial week
                          </Badge>
                          <Text size="xs" c="dimmed">
                            Through report time
                          </Text>
                        </>
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
                      <WeekCoverageCell
                        key={week.week_start}
                        counts={weekCounts(source, week)}
                      />
                    ))}
                  </Table.Tr>
                ))}
              </Table.Tbody>
              <Table.Tfoot>
                <Table.Tr>
                  <Table.Th scope="row">All observed sources</Table.Th>
                  {weeks.map((week) => (
                    <WeekCoverageCell key={week.week_start} counts={week} />
                  ))}
                </Table.Tr>
              </Table.Tfoot>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      </Paper>
    </Stack>
  );
}

function WeekCoverageCell({
  counts
}: {
  counts: Pick<StatsIngestionWeek, "records" | "with_refinement" | "pending">;
}) {
  return (
    <Table.Td>
      <Text size="sm" fw={counts.records > 0 ? 600 : 400}>
        {formatCount(counts.records)} captured
      </Text>
      <Text size="xs" c="dimmed">
        {formatCount(counts.with_refinement)} refined · {formatCount(counts.pending)} pending
      </Text>
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
    <Stack gap="md" component="section" aria-labelledby="status-refinement-heading">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Title order={2} size="h4" id="status-refinement-heading">
          Refinement output
        </Title>
        <Badge variant="light" color="wood">
          Output item counts
        </Badge>
      </Group>

      <Text size="sm" c="dimmed">
        These are current refinement output item counts, not processed raw records, lifetime
        throughput, or job completion figures.
      </Text>

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
          <Text size="xs" c="dimmed">
            Event items include past events and are not deduplicated across sources. One raw
            record may yield several output items, so neither this count nor displayed calendar
            occurrences equal records processed.
          </Text>

          <Text size="sm">
            Latest refinement result:{" "}
            <Text component="span" fw={600}>
              {formatTimestamp(totals.last_refined_at, timeZone)}
            </Text>
          </Text>
          <Text size="xs" c="dimmed">
            A stored refinement does not by itself indicate a successful or high-quality result.
            Coverage is not a success rate.
          </Text>
        </Stack>
      </Paper>

      <Alert color="gray" variant="light" title="Storage timestamps are not sync times">
        <Text size="sm">
          Latest captured record and latest refinement result are storage timestamps, not sync
          times. No freshness or health claim is made here.
        </Text>
      </Alert>

      <Paper withBorder p="md" bg="white">
        <Stack gap="sm">
          <Text fw={600}>Refinement output by source</Text>
          <Table.ScrollContainer
            minWidth={900}
            type="native"
            role="region"
            tabIndex={0}
            aria-label="Refinement output items by source"
          >
            <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
              <Table.Caption>
                Current refinement output items by observed source. Item counts are not raw
                record counts, and the latest refinement result is not a sync time.
              </Table.Caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Source</Table.Th>
                  <Table.Th scope="col">Refined items</Table.Th>
                  <Table.Th scope="col">Event</Table.Th>
                  <Table.Th scope="col">Advertisement</Table.Th>
                  <Table.Th scope="col">Announcement</Table.Th>
                  <Table.Th scope="col">Non-event</Table.Th>
                  <Table.Th scope="col">Unknown</Table.Th>
                  <Table.Th scope="col">Latest refinement result</Table.Th>
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
              <Table.Tfoot>
                <Table.Tr>
                  <Table.Th scope="row">All observed sources</Table.Th>
                  <Table.Td>{formatCount(totals.refinement_items_total)}</Table.Td>
                  <Table.Td>{formatCount(totals.refinement_items_by_kind.event)}</Table.Td>
                  <Table.Td>{formatCount(totals.refinement_items_by_kind.advertisement)}</Table.Td>
                  <Table.Td>{formatCount(totals.refinement_items_by_kind.announcement)}</Table.Td>
                  <Table.Td>{formatCount(totals.refinement_items_by_kind.non_event)}</Table.Td>
                  <Table.Td>{formatCount(totals.refinement_items_by_kind.unknown)}</Table.Td>
                  <Table.Td>{formatTimestamp(totals.last_refined_at, timeZone)}</Table.Td>
                </Table.Tr>
              </Table.Tfoot>
            </Table>
          </Table.ScrollContainer>
        </Stack>
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

function SourceSyncSection({ sources }: { sources: StatsSource[] }) {
  return (
    <Stack gap="md" component="section" aria-labelledby="status-sync-heading">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Title order={2} size="h4" id="status-sync-heading">
          Source sync
        </Title>
        <Badge variant="light" color="gray">
          Recorded attempts
        </Badge>
      </Group>

      <Text size="sm" c="dimmed">
        Last recorded sync attempt and last successful completion per source. Fetched and
        stored counts describe source ingestion only. A successful sync can leave newly stored
        records pending refinement; it does not mean refinement or media upload has completed.
        No schedule, availability, or freshness is inferred.
      </Text>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={1080}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="Recorded source sync attempts and last successful completion"
        >
          <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
            <Table.Caption>
              “No sync recorded” means no attempt is stored, not a failure. An unfinished
              attempt has no recorded completion and is not claimed to be running. A later
              failure does not erase the prior successful completion.
            </Table.Caption>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">Source</Table.Th>
                <Table.Th scope="col">Last attempt</Table.Th>
                <Table.Th scope="col">Attempt time (UTC)</Table.Th>
                <Table.Th scope="col">Attempt counts</Table.Th>
                <Table.Th scope="col">Last successful sync (UTC)</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {sources.map((source) => (
                <SourceSyncRow key={source.source} source={source} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      <Alert color="gray" variant="light" title="Sync is not refinement or media freshness">
        <Text size="sm">
          Source sync records whether a fetch/storage attempt was started and completed. It
          does not measure refinement quality or backlog, and media-upload freshness is not
          tracked here. Latest capture and latest refinement result remain separate storage
          timestamps.
        </Text>
      </Alert>
    </Stack>
  );
}

function SourceSyncRow({ source }: { source: StatsSource }) {
  const sync = source.sync;
  const attempt = sync.last_attempt;

  return (
    <Table.Tr>
      <Table.Th scope="row">{source.source}</Table.Th>
      <Table.Td>
        <Badge variant="light" color="gray" size="sm">
          {SYNC_STATE_LABELS[sync.state]}
        </Badge>
        {attempt?.failure_stage && (
          <Text size="xs" c="dimmed">
            Failure stage: {attempt.failure_stage}
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {attempt ? (
          <>
            <Text size="sm">Started {formatTimestamp(attempt.started_at, "UTC")}</Text>
            <Text size="xs" c="dimmed">
              {attempt.completed_at
                ? `Completed ${formatTimestamp(attempt.completed_at, "UTC")}`
                : "Completion not recorded"}
            </Text>
          </>
        ) : (
          <Text size="sm" c="dimmed">
            No attempt recorded
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
            <>
              <Text size="sm">Fetched {formatCount(attempt.fetched_count)}</Text>
              <Text size="xs" c="dimmed">
                Stored {formatCount(attempt.inserted_count)} · Duplicates{" "}
                {formatCount(attempt.duplicate_count)}
              </Text>
            </>
          )
        ) : (
          <Text size="sm" c="dimmed">
            No attempt recorded
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {sync.last_success ? (
          <>
            <Text size="sm">{formatTimestamp(sync.last_success.completed_at, "UTC")}</Text>
            <Text size="xs" c="dimmed">
              Fetched {formatCount(sync.last_success.fetched_count)} · Stored{" "}
              {formatCount(sync.last_success.inserted_count)} · Duplicates{" "}
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

function CitySection({ data }: { data: StatsResponse }) {
  const assignedTotal = data.cities.reduce(
    (total, city) => total + city.event_items_total,
    0
  );

  return (
    <Stack gap="md" component="section" aria-labelledby="status-cities-heading">
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Title order={2} size="h4" id="status-cities-heading">
          City event items
        </Title>
        <Badge variant="light" color="wood">
          Refined event items
        </Badge>
      </Group>

      <Text size="sm" c="dimmed">
        City rows count current refined event items assigned to each published city, all time.
        Raw records are not assigned to a city before refinement, so no city-level ingestion or
        backlog figures are inferred.
      </Text>

      <Paper withBorder p="md" bg="white">
        <Table.ScrollContainer
          minWidth={680}
          type="native"
          role="region"
          tabIndex={0}
          aria-label="Refined event items by city"
        >
          <Table striped highlightOnHover verticalSpacing="xs" horizontalSpacing="sm" tabularNums>
            <Table.Caption>
              Refined event items by published city. Counts are all time and not deduplicated
              across sources.
            </Table.Caption>
            <Table.Thead>
              <Table.Tr>
                <Table.Th scope="col">City</Table.Th>
                <Table.Th scope="col">Refined event items</Table.Th>
                <Table.Th scope="col">Sources with event items</Table.Th>
                <Table.Th scope="col">Browse</Table.Th>
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
        <Badge variant="light">Published cities: {formatCount(data.supported_cities_total)}</Badge>
        <Badge variant="light" color="gray">
          Unassigned event items: {formatCount(data.unassigned_city_event_items_total)}
        </Badge>
        <Badge variant="light" color="gray">
          Unsupported city event items: {formatCount(data.unsupported_city_event_items_total)}
        </Badge>
      </Group>

      <Text size="xs" c="dimmed">
        Published city totals ({formatCount(assignedTotal)}) plus the unassigned
        ({formatCount(data.unassigned_city_event_items_total)}) and unsupported
        ({formatCount(data.unsupported_city_event_items_total)}) buckets add up to the refined
        event item total ({formatCount(data.totals.refinement.event_items_total)}). “Unassigned”
        means refinement assigned no city; “unsupported” means a city outside the published
        registry.
      </Text>
    </Stack>
  );
}

function CityRow({ city }: { city: StatsCity }) {
  return (
    <Table.Tr>
      <Table.Th scope="row">
        <Text fw={600}>{city.name}</Text>
        <Text size="xs" c="dimmed">
          {city.city_id} · {city.timezone}
        </Text>
      </Table.Th>
      <Table.Td>{formatCount(city.event_items_total)}</Table.Td>
      <Table.Td>{formatCount(city.sources_with_event_items)}</Table.Td>
      <Table.Td>
        <Anchor
          component={Link}
          to={`/${city.country_code}/${city.slug}`}
          aria-label={`Browse ${city.name} events`}
        >
          Browse {city.name}
        </Anchor>
      </Table.Td>
    </Table.Tr>
  );
}

function weekCounts(
  source: StatsSource,
  week: StatsIngestionWeek
): Pick<StatsIngestionWeek, "records" | "with_refinement" | "pending"> {
  return (
    source.weeks.find((entry) => entry.week_start === week.week_start) ?? {
      records: 0,
      with_refinement: 0,
      pending: 0
    }
  );
}

function pendingOutsideWindow(weeks: StatsIngestionWeek[], pendingTotal: number): number {
  const pendingInside = weeks.reduce((total, week) => total + week.pending, 0);
  return Math.max(0, pendingTotal - pendingInside);
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
  const label = formatInTimeZone(
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
  return `${label} (${timeZone})`;
}
