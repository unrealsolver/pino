import { Button, Group, MultiSelect, NumberInput, Paper, TextInput } from "@mantine/core";
import { DateTimePicker } from "@mantine/dates";
import type { UseFormReturnType } from "@mantine/form";
import { Search } from "lucide-react";

import type { EventFilters } from "../../api";
import { defaultDateTo, todayMorning } from "../../eventUtils";
import { createDefaultEventFilters } from "./utils";

export function EventFiltersForm({
  categories,
  form
}: {
  categories: string[];
  form: UseFormReturnType<EventFilters>;
}) {
  const filters = form.values;

  return (
    <Paper withBorder p="sm" bg="amber.0">
      <Group align="end" gap="sm" wrap="wrap">
        <MultiSelect
          className="filterControl filterWide"
          label="Tags"
          placeholder="Any category"
          data={categories}
          value={filters.categories}
          onChange={(categories) => form.setFieldValue("categories", categories)}
          searchable
          clearable
          comboboxProps={{ withinPortal: false }}
        />
        <NumberInput
          className="filterControl filterScore"
          label="Score"
          min={0}
          max={1}
          step={0.1}
          decimalScale={2}
          value={filters.minScore}
          onChange={(value) =>
            form.setFieldValue("minScore", typeof value === "number" ? value : 0)
          }
        />
        <TextInput
          className="filterControl filterWide"
          label="Text"
          placeholder="Search title, summary, text"
          leftSection={<Search size={16} />}
          value={filters.query}
          onChange={(event) => form.setFieldValue("query", event.currentTarget.value)}
        />
        <DateTimePicker
          className="filterControl filterDate"
          label="From"
          valueFormat="YYYY-MM-DD HH:mm"
          value={filters.dateFrom}
          onChange={(value) => {
            const dateFrom = coercePickerDate(value) ?? todayMorning();
            form.setValues({
              ...form.values,
              dateFrom,
              dateTo: defaultDateTo(dateFrom)
            });
          }}
        />
        <DateTimePicker
          className="filterControl filterDate"
          label="To"
          valueFormat="YYYY-MM-DD HH:mm"
          value={filters.dateTo}
          onChange={(value) =>
            form.setFieldValue(
              "dateTo",
              coercePickerDate(value) ?? defaultDateTo(form.values.dateFrom)
            )
          }
        />
        <Button variant="light" onClick={() => form.setValues(createDefaultEventFilters())}>
          Reset
        </Button>
      </Group>
    </Paper>
  );
}

function coercePickerDate(value: Date | string | null): Date | null {
  if (value instanceof Date) {
    return value;
  }
  if (typeof value === "string" && value) {
    return new Date(value);
  }
  return null;
}
