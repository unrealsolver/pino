import { Button, Group, MultiSelect, NumberInput, Paper, TextInput } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import { Search } from "lucide-react";
import { useMemo } from "react";

import type { EventFilters } from "../../api";
import { MAX_EVENT_FILTER_QUERY_LENGTH } from "../../eventFilterUrl";

export function EventFiltersForm({
  categories,
  filters,
  onCategoriesChange,
  onScoreChange,
  onQueryChange,
  onDateFromChange,
  onDateToChange,
  onReset
}: {
  categories: string[];
  filters: EventFilters;
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
        <DateTimePicker
          flex="1 1 calc(var(--mantine-spacing-xl) * 6)"
          miw="calc(var(--mantine-spacing-xl) * 7)"
          label="From"
          valueFormat="YYYY-MM-DD HH:mm"
          value={filters.dateFrom}
          onChange={onDateFromChange}
        />
        <DateTimePicker
          flex="1 1 calc(var(--mantine-spacing-xl) * 6)"
          miw="calc(var(--mantine-spacing-xl) * 7)"
          label="To"
          valueFormat="YYYY-MM-DD HH:mm"
          value={filters.dateTo}
          onChange={onDateToChange}
        />
        <Button variant="light" onClick={onReset}>
          Reset
        </Button>
      </Group>
    </Paper>
  );
}
