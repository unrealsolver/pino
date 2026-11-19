import { Box, CloseButton, Image, Modal, Paper, Text } from "@mantine/core";

import type { EventItem } from "../../api";
import classes from "./PosterPreview.module.css";

export function PosterPreview({ event, onClose }: { event: EventItem | null; onClose: () => void }) {
  const posterSrc = event?.images?.[0];
  return (
    <Modal
      opened={Boolean(posterSrc)}
      onClose={onClose}
      withCloseButton={false}
      attributes={{ content: { "aria-label": event?.title || "Event poster" } }}
      classNames={{ content: classes.posterSurface }}
      removeScrollProps={{ allowPinchZoom: true }}
      size="xl"
      padding="0"
      shadow="none"
    >
      {event && posterSrc && (
        <Paper
          component="figure"
          radius="md"
          bg="transparent"
          m={0}
          mx="auto"
          w="fit-content"
          maw="100%"
          style={{ overflow: "hidden" }}
        >
          <Box pos="relative">
            <Image
              src={posterSrc}
              alt="Event poster"
              fit="contain"
              w="auto"
              maw="100%"
              mah="calc(100dvh - 6rem)"
            />

            <CloseButton
              className={classes.posterClose}
              size="xl"
              aria-label="Close poster"
              radius="xl"
              onClick={onClose}
            />
          </Box>
          <Box component="figcaption" className={classes.posterCaption} bg="wood.0">
            <Text size="sm" fw={600} ta="center" px="sm" py="xs">
              {event.title}
            </Text>
          </Box>
        </Paper>
      )}
    </Modal>
  );
}
