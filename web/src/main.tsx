import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "./styles.css";

import { QueryClient } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";

if (import.meta.env.PROD) {
  void import("@plausible-analytics/tracker")
    .then(({ init }) => {
      init({
        domain: "pino.based.lt",
        endpoint: "https://analytics.based.lt/api/event"
      });
    })
    .catch((error: unknown) => {
      console.warn("Analytics initialization failed", error);
    });
}

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App queryClient={queryClient} />
  </React.StrictMode>
);
