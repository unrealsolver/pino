# Web UI
This spec only covers non-Pino enabled UI

# Goal
Have a Web UI that allow to query DB with filters to see what events are available.
Serves as debug for Pino and also good-enough substitute for the assistant.

# Agent notes
# Step 0
Review spec for gaps.
# Step 1
Before starting coding review and ask access to any MCP or tools you need.
# Step 3
proceed

# Stack
SPA

## FE
bun
React
React router
Vite
Mantine (no Tailwind)
TanStack Query for API/server state
TanStack Virtual for large event lists
Mantine MCP: https://mantine.dev/guides/llms/
NO React Server Components!

# BE
Postgres we already have. Keys we already have.
Use FastAPI for the API.
No auth yet.
Add throttling to 60 rpm
Make sure impossibility of injections
Make reasonable API hardening to avoid unexpected malicious use / breakig in. Do not go too hard as all services would be deployed with SystemD isolation and hardening anyway.

# UI/UX
A single route `/event/` with a events split by days with thin horizontal line and capital thin text as header
Header has filters:
- tag selector for predefined list of categories we capture
- score input
- text imatch
- date range. Default start date is today morning and default end date is +30 days
- end of event list has `Next month` button that extends the end date by another 30 days

Each event line is a a time duration, title and category tags. Per each day section events sorted by start time.
Each line has a rectangular tinted background with a gap between lines
Large lists should be virtualized.

# Style
I want amber/wood tonal palette. Work with Mantine theme object to achieve that. Prefer `rem`s for dimensions.

# Tests
Unit tests required

# Running locally
All configs data already allows to run everything locally
