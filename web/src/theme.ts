import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "amber",
  defaultRadius: "sm",
  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  headings: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    fontWeight: "600"
  },
  radius: {
    xs: rem(2),
    sm: rem(4),
    md: rem(6),
    lg: rem(8),
    xl: rem(8)
  },
  // TODO make new pallette: cloudy blue, pink and chick-yellow accents
  colors: {
    amber: [
      "#fff7e2",
      "#fdeecf",
      "#f9dca1",
      "#f5ca73",
      "#f1b845",
      "#efad2a",
      "#efa81a",
      "#d4930b",
      "#bd8201",
      "#a46f00"
    ],
    wood: [
      "#fff5e6",
      "#f7e8d6",
      "#ead0b0",
      "#ddb787",
      "#d2a164",
      "#cb934d",
      "#c98d42",
      "#b17831",
      "#9e6a29",
      "#8a5b1d"
    ]
  },
  components: {
    Button: {
      defaultProps: {
        radius: "sm"
      }
    },
    Paper: {
      defaultProps: {
        radius: "sm"
      }
    },
    Select: {
      defaultProps: {
        radius: "sm"
      }
    },
    TextInput: {
      defaultProps: {
        radius: "sm"
      }
    },
    NumberInput: {
      defaultProps: {
        radius: "sm"
      }
    }
  }
});
