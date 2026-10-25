import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { CityRoute } from "./routes/CityRoute";
import { theme } from "./theme";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="*" element={<CityRoute />} />
    </Routes>
  );
}

export function AppProviders({
  queryClient,
  children
}: {
  queryClient: QueryClient;
  children: React.ReactNode;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <DatesProvider settings={{ locale: "en", firstDayOfWeek: 1, weekendDays: [0, 6] }}>
          {children}
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}

export function App({ queryClient }: { queryClient: QueryClient }) {
  return (
    <AppProviders queryClient={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  );
}
