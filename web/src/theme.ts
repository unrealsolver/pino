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
  colors: {
    amber: [
      "#fff7e7",
      "#f4ead7",
      "#e8d3ad",
      "#dcbc82",
      "#d3a85e",
      "#cd9b46",
      "#ca9438",
      "#b27f2c",
      "#9f7024",
      "#895f19"
    ],
    wood: [
      "#f8f2ea",
      "#eadfce",
      "#d7c2a1",
      "#c5a471",
      "#b99051",
      "#b2833d",
      "#ad7c32",
      "#996b27",
      "#895e20",
      "#764f16"
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
