import { CloseButton, Popover, Stack, TextInput } from "@mantine/core";
import { DatePicker, TimeInput } from "@mantine/dates";
import { useDisclosure } from "@mantine/hooks";

/**
 * A compact city wall-clock picker.
 *
 * Mantine's DateTimePicker normalizes through browser-local dayjs values, which
 * silently shifts city times when the browser is in a different DST period. This
 * composed picker keeps raw `YYYY-MM-DD HH:mm:ss` city wall strings: the calendar
 * returns date-only strings and TimeInput returns raw `HH:mm` strings.
 */
export function CityDateTimePicker({
  label,
  value,
  error,
  onChange
}: {
  label: string;
  value: string | null;
  error?: string;
  onChange: (value: string | null) => void;
}) {
  const [opened, { open, close, toggle }] = useDisclosure(false);
  const datePart = value ? value.slice(0, 10) : null;
  const timePart = value && value.length >= 16 ? value.slice(11, 16) : "";
  const displayValue = datePart ? `${datePart} ${timePart}` : "";
  // Mantine's calendar uses dayjs date-only parsing, which maps years 00–99 to
  // 1900–1999. Native date inputs preserve these supported URL years literally.
  const needsLiteralDateInput = Boolean(datePart && Number(datePart.slice(0, 4)) < 100);

  function applyDate(nextDate: string | null) {
    if (!nextDate) {
      onChange(null);
      return;
    }
    onChange(`${nextDate} ${timePart || "00:00"}:00`);
  }

  function applyTime(nextTime: string) {
    if (!datePart || !nextTime) {
      return;
    }
    const withSeconds = nextTime.length === 5 ? `${nextTime}:00` : nextTime.slice(0, 8);
    onChange(`${datePart} ${withSeconds}`);
  }

  return (
    <Popover
      opened={opened}
      onChange={(nextOpened) => (nextOpened ? open() : close())}
      position="bottom-start"
      withinPortal={false}
      shadow="md"
      transitionProps={{ duration: 0 }}
    >
      <Popover.Target>
        <TextInput
          label={label}
          value={displayValue}
          readOnly
          error={error}
          onClick={open}
          onFocus={open}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              toggle();
            }
          }}
          aria-haspopup="dialog"
          aria-expanded={opened}
          rightSection={
            value ? (
              <CloseButton
                size="sm"
                aria-label={`Clear ${label}`}
                onMouseDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  onChange(null);
                }}
              />
            ) : undefined
          }
        />
      </Popover.Target>
      <Popover.Dropdown>
        <Stack gap="sm" w="calc(var(--mantine-spacing-xl) * 8)">
          {needsLiteralDateInput ? (
            <TextInput
              type="date"
              label={`${label} date`}
              value={datePart ?? ""}
              onChange={(event) => applyDate(event.currentTarget.value || null)}
            />
          ) : <DatePicker
            value={datePart}
            onChange={applyDate}
            allowDeselect={false}
            defaultDate={datePart ?? undefined}
          />}
          <TimeInput
            aria-label={`${label} time`}
            value={timePart}
            onChange={(event) => applyTime(event.currentTarget.value)}
            withSeconds={false}
          />
        </Stack>
      </Popover.Dropdown>
    </Popover>
  );
}
