import { Box, Button, Group, MultiSelect, NumberInput, Paper, TextInput } from "@mantine/core";
import { Search } from "lucide-react";
import { useMemo } from "react";

import type { EventFilters } from "../../api";
import { MAX_EVENT_FILTER_QUERY_LENGTH } from "../../eventFilterUrl";
import { formatPickerValue } from "../../timezone";
import { CityDateTimePicker } from "./CityDateTimePicker";

export function EventFiltersForm({
  categories,
  filters,
  timeZone,
  dateFromError,
  dateToError,
  onCategoriesChange,
  onScoreChange,
  onQueryChange,
  onDateFromChange,
  onDateToChange,
  onReset
}: {
  categories: string[];
  filters: EventFilters;
  timeZone: string;
  dateFromError?: string;
  dateToError?: string;
  onCategoriesChange: (categories: string[]) => void;
  onScoreChange: (score: number) => void;
  onQueryChange: (query: string) => void;
  onDateFromChange: (value: Date | string | null) => void;
  onDateToChange: (value: Date | string | null) => void;
  onReset: () => void;
}) {
  // Keep URL-provided names selectable even before the category metadata loads.
  const categoryOptions = useMemo(
    () => [...new Set([...categories, ...filters.categories])],
    [categories, filters.categories]
  );

  return (
    <Paper withBorder p="sm" bg="amber.0">
      <Group align="end" gap="sm" wrap="wrap">
        <MultiSelect
          flex="1 1 calc(var(--mantine-spacing-xl) * 6)"
          miw="calc(var(--mantine-spacing-xl) * 8)"
          label="Tags"
          placeholder="Any category"
          data={categoryOptions}
          value={filters.categories}
          onChange={onCategoriesChange}
          searchable
          clearable
          comboboxProps={{ withinPortal: false }}
        />
        <NumberInput
          flex="0 0 calc(var(--mantine-spacing-xl) * 3.25)"
          label="Score"
          min={0}
          max={1}
          step={0.1}
          decimalScale={2}
          value={filters.minScore}
          onChange={(value) => onScoreChange(typeof value === "number" ? value : 0)}
        />
        <TextInput
          flex="1 1 calc(var(--mantine-spacing-xl) * 6)"
          miw="calc(var(--mantine-spacing-xl) * 8)"
          label="Text"
          placeholder="Search title, summary, text"
          leftSection={<Search size={16} />}
          maxLength={MAX_EVENT_FILTER_QUERY_LENGTH}
          value={filters.query}
          onChange={(event) => onQueryChange(event.currentTarget.value)}
        />
        <Box flex="1 1 calc(var(--mantine-spacing-xl) * 6)" miw="calc(var(--mantine-spacing-xl) * 7)">
          <CityDateTimePicker
            label="From"
            value={formatPickerValue(filters.dateFrom, timeZone)}
            error={dateFromError}
            onChange={onDateFromChange}
          />
        </Box>
        <Box flex="1 1 calc(var(--mantine-spacing-xl) * 6)" miw="calc(var(--mantine-spacing-xl) * 7)">
          <CityDateTimePicker
            label="To"
            value={filters.dateTo ? formatPickerValue(filters.dateTo, timeZone) : null}
            error={dateToError}
            onChange={onDateToChange}
          />
        </Box>
        <Button variant="light" onClick={onReset}>
          Reset
        </Button>
      </Group>
    </Paper>
  );
}
