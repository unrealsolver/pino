import { Paper, Text } from "@mantine/core";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { EventLine } from "./EventLine";
import { HiddenDayControl } from "./HiddenDayControl";
import type { VirtualListItem } from "./utils";

export function VirtualEventList({
  items,
  hiddenEventIds,
  onHideEvent,
  onShowEvent
}: {
  items: VirtualListItem[];
  hiddenEventIds: Set<string>;
  onHideEvent: (eventId: string) => void;
  onShowEvent: (eventId: string) => void;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const [scrollMargin, setScrollMargin] = useState(0);
  const getVirtualItemKey = useCallback((index: number) => items[index]?.key ?? index, [items]);
  const updateScrollMargin = useCallback(() => {
    const nextScrollMargin = listRef.current?.offsetTop ?? 0;
    setScrollMargin((current) => (current === nextScrollMargin ? current : nextScrollMargin));
  }, []);

  useLayoutEffect(() => {
    updateScrollMargin();
  });

  useLayoutEffect(() => {
    window.addEventListener("resize", updateScrollMargin);
    return () => window.removeEventListener("resize", updateScrollMargin);
  }, [updateScrollMargin]);

  const virtualizer = useWindowVirtualizer({
    count: items.length,
    estimateSize: (index) => (items[index]?.type === "day" ? 40 : 82),
    getItemKey: getVirtualItemKey,
    overscan: 12,
    scrollMargin
  });

  return (
    <div ref={listRef} className="virtualList" style={{ height: virtualizer.getTotalSize() }}>
      {virtualizer.getVirtualItems().map((virtualRow) => {
        const item = items[virtualRow.index];
        if (!item) {
          return null;
        }
        return (
          <div
            key={virtualRow.key}
            className="virtualRow"
            data-index={virtualRow.index}
            ref={virtualizer.measureElement}
            style={{
              transform: `translateY(${virtualRow.start - virtualizer.options.scrollMargin}px)`
            }}
          >
            {item.type === "day" ? (
              <Paper className="dayHeader" withBorder p="xs" bg="wood.1" radius="sm">
                <Text component="h2" c="wood.9" size="sm" fw={700} m={0}>
                  {item.day.label}
                </Text>
                <HiddenDayControl occurrences={item.day.events} hiddenEventIds={hiddenEventIds} />
              </Paper>
            ) : (
              <EventLine
                occurrence={item.occurrence}
                isHidden={hiddenEventIds.has(item.occurrence.event.id)}
                onToggleHidden={() =>
                  hiddenEventIds.has(item.occurrence.event.id)
                    ? onShowEvent(item.occurrence.event.id)
                    : onHideEvent(item.occurrence.event.id)
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
