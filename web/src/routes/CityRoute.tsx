import { Alert, Anchor, Button, Container, Group, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useLocation } from "react-router-dom";

import { CITIES_QUERY_KEY, fetchCities } from "../api";
import { parseCityPath } from "../cityRoutes";
import { EventRoute } from "./EventRoute";

export function CityRoute() {
  const location = useLocation();
  const resolution = parseCityPath(location.pathname);

  if (resolution.kind === "entry") {
    return (
      <Navigate
        to={{ pathname: "/vilnius", search: location.search, hash: location.hash }}
        replace
      />
    );
  }

  if (resolution.kind === "unknown") {
    return <CityNotFound pathname={location.pathname} />;
  }

  if (resolution.normalizedPath !== location.pathname) {
    return (
      <Navigate
        to={{ pathname: resolution.normalizedPath, search: location.search, hash: location.hash }}
        replace
      />
    );
  }

  return <CityFeed cityId={resolution.cityId} />;
}

function CityFeed({ cityId }: { cityId: string }) {
  const citiesQuery = useQuery({
    queryKey: CITIES_QUERY_KEY,
    queryFn: ({ signal }) => fetchCities({ signal })
  });

  if (citiesQuery.isPending) {
    return (
      <StatusShell>
        <Group justify="center" py="xl">
          <Loader color="amber" />
          <Text c="dimmed">Loading city…</Text>
        </Group>
      </StatusShell>
    );
  }

  if (citiesQuery.isError) {
    const message = citiesQuery.error instanceof Error
      ? citiesQuery.error.message
      : "Could not load city metadata";
    return (
      <StatusShell>
        <Alert color="red" variant="light" title="City metadata unavailable">
          <Stack gap="sm" align="flex-start">
            <Text>{message}</Text>
            <Button
              variant="light"
              loading={citiesQuery.isFetching}
              onClick={() => {
                void citiesQuery.refetch();
              }}
            >
              Retry
            </Button>
          </Stack>
        </Alert>
      </StatusShell>
    );
  }

  const city = citiesQuery.data.cities.find((entry) => entry.id === cityId);
  if (!city) {
    return <CityNotFound pathname={cityId} />;
  }

  return <EventRoute city={city} />;
}

function CityNotFound({ pathname }: { pathname: string }) {
  return (
    <StatusShell>
      <Paper withBorder p="xl" bg="amber.0" data-testid="city-not-found">
        <Stack gap="sm">
          <Title order={1} size="h3">
            City not found
          </Title>
          <Text>
            There is no supported city feed at <strong>{pathname}</strong>.
          </Text>
          <Text size="sm" c="dimmed">
            Only published cities can be browsed.{" "}
            <Anchor component={Link} to="/vilnius">
              Browse Vilnius
            </Anchor>
            .
          </Text>
        </Stack>
      </Paper>
    </StatusShell>
  );
}

function StatusShell({ children }: { children: React.ReactNode }) {
  return (
    <Container size="xl" px="lg" py="xl">
      {children}
    </Container>
  );
}
