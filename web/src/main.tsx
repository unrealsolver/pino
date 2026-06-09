import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "./styles.css";

import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { EventRoute } from "./routes/EventRoute";
import { theme } from "./theme";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <MantineProvider theme={theme} defaultColorScheme="light">
        <DatesProvider settings={{ locale: "en", firstDayOfWeek: 1, weekendDays: [0, 6] }}>
          <BrowserRouter>
            <Routes>
              <Route path="/event/" element={<EventRoute />} />
              <Route path="*" element={<Navigate to="/event/" replace />} />
            </Routes>
          </BrowserRouter>
        </DatesProvider>
      </MantineProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
