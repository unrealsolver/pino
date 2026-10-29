/**
 * Explicit city route parsing. Short aliases are deliberately manual: city names
 * can be ambiguous across countries, so only registered slugs are accepted.
 */
export const SHORT_CITY_ALIASES: Readonly<Record<string, string>> = {
  vilnius: "lt/vilnius"
};

/** System/entry paths win over any future short city alias with the same name. */
export const RESERVED_PATH_SEGMENTS = new Set(["event", "api", "media", "assets", "status"]);

export type CityPathResolution =
  | { kind: "entry" }
  | { kind: "city"; cityId: string; normalizedPath: string }
  | { kind: "unknown"; reason: "reserved" | "path" | "alias" | "country" | "city" };

export function parseCityPath(pathname: string): CityPathResolution {
  if (pathname === "/") {
    return { kind: "entry" };
  }

  const trimmed = pathname.replace(/\/+$/, "");
  const segments = trimmed.split("/").filter(Boolean);

  if (segments.length === 0) {
    return { kind: "entry" };
  }

  // Entry redirects are exact lowercase paths; unknown casing is not a fallback.
  if (segments.length === 1 && (segments[0] === "lt" || segments[0] === "event")) {
    return { kind: "entry" };
  }

  if (segments.some((segment) => RESERVED_PATH_SEGMENTS.has(segment.toLowerCase()))) {
    return { kind: "unknown", reason: "reserved" };
  }

  if (segments.length === 1) {
    const shortSlug = segments[0].toLowerCase();
    const cityId = SHORT_CITY_ALIASES[shortSlug];
    if (!cityId) {
      return { kind: "unknown", reason: "alias" };
    }
    return { kind: "city", cityId, normalizedPath: `/${shortSlug}` };
  }

  if (segments.length === 2) {
    const [country, city] = segments.map((segment) => segment.toLowerCase());
    return {
      kind: "city",
      cityId: `${country}/${city}`,
      normalizedPath: `/${country}/${city}`
    };
  }

  return { kind: "unknown", reason: "path" };
}
