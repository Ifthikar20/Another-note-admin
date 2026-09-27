/**
 * How numbers, money, sizes, durations, times and identities are written everywhere.
 *
 * Numbers: thousands separators ("1,284"), compact in stat tiles ("18.2M").
 * Money: US dollars to two decimals ("$41.27"); an unknown price is "—", never "$0.00".
 * Times: stored in UTC, shown in the viewer's own time zone, relative ("3 h ago") with
 * the exact time on hover. Daily charts count UTC days, and say so.
 */

const DASH = "—";
const LOCALE = "en-GB";

const integer = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const oneDecimal = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });

type Maybe<T> = T | null | undefined;

export function formatInt(n: Maybe<number>): string {
  return n === null || n === undefined || Number.isNaN(n) ? DASH : integer.format(Math.round(n));
}

/** 1,284 / 12.9K / 18.2M / 1.3B: for stat tiles and axis ticks. */
export function formatCompact(n: Maybe<number>): string {
  if (n === null || n === undefined || Number.isNaN(n)) return DASH;
  const abs = Math.abs(n);
  if (abs < 10_000) return integer.format(Math.round(n));
  const units: [number, string][] = [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ];
  for (const [size, unit] of units) {
    if (abs >= size) return `${oneDecimal.format(n / size)}${unit}`;
  }
  return integer.format(n);
}

/** "$41.27"; "<$0.01" for a real but tiny amount; "—" when the price is unknown. */
export function formatMoney(value: Maybe<number>): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  if (value > 0 && value < 0.005) return "<$0.01";
  return usd.format(value);
}

/** For tiles: "$41.27", "$1.2K", "$903". */
export function formatMoneyCompact(value: Maybe<number>): string {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  if (Math.abs(value) >= 10_000) return `$${formatCompact(value)}`;
  return formatMoney(value);
}

/** Bytes in decimal units, as storage is billed: "81.2 MB", "18.2 GB". */
export function formatBytes(n: Maybe<number>): string {
  if (n === null || n === undefined || Number.isNaN(n)) return DASH;
  if (n < 1000) return `${integer.format(n)} B`;
  const units = ["KB", "MB", "GB", "TB", "PB"];
  let value = n;
  let unit = "B";
  for (const u of units) {
    if (value < 1000) break;
    value /= 1000;
    unit = u;
  }
  return `${oneDecimal.format(value)} ${unit}`;
}

/** Seconds as "45 s", "12 min", "1 h 5 min", "2 d 3 h". */
export function formatDuration(seconds: Maybe<number>): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return DASH;
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
  const days = Math.floor(hours / 24);
  return hours % 24 ? `${days} d ${hours % 24} h` : `${days} d`;
}

/** Transcribed audio: milliseconds as minutes, "12.5 min". */
export function formatAudioMinutes(ms: Maybe<number>): string {
  if (ms === null || ms === undefined || Number.isNaN(ms)) return DASH;
  return `${oneDecimal.format(ms / 60_000)} min`;
}

/** An age in hours: "40 min", "20.5 h", "3.2 d". */
export function formatHours(hours: Maybe<number>): string {
  if (hours === null || hours === undefined || Number.isNaN(hours)) return DASH;
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${oneDecimal.format(hours)} h`;
  return `${oneDecimal.format(hours / 24)} d`;
}

const RELATIVE: [number, Intl.RelativeTimeFormatUnit][] = [
  [60, "second"],
  [60, "minute"],
  [24, "hour"],
  [7, "day"],
  [4.34524, "week"],
  [12, "month"],
  [Number.POSITIVE_INFINITY, "year"],
];

/** "just now", "5 minutes ago", "in 3 hours", "2 days ago"; `short` gives "2 hr. ago" for tables. */
export function formatRelative(iso: Maybe<string>, now: number = Date.now(), style: "long" | "short" = "long"): string {
  if (!iso) return DASH;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return DASH;
  let delta = (then - now) / 1000;
  if (Math.abs(delta) < 45) return "just now";
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style });
  for (const [size, unit] of RELATIVE) {
    if (Math.abs(delta) < size) return rtf.format(Math.round(delta), unit);
    delta /= size;
  }
  return rtf.format(Math.round(delta), "year");
}

/** The exact moment, in the viewer's own time zone: "31 Oct 2026, 14:05:09". */
export function formatDateTime(iso: Maybe<string>, timeZone?: string): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZone,
  }).format(d);
}

/** Shorter, for tables: "31 Oct, 14:05" (or with the year when it isn't this year). */
export function formatShortDateTime(iso: Maybe<string>, timeZone?: string, now: Date = new Date()): string {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  const sameYear = d.getFullYear() === now.getFullYear();
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    year: sameYear ? undefined : "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(d);
}

/** A UTC day ("2026-10-31") as "31 Oct". It stays that day wherever the viewer is. */
export function formatDay(day: Maybe<string>): string {
  if (!day) return DASH;
  const d = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return DASH;
  return new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", timeZone: "UTC" }).format(d);
}

/** "Fri 31 Oct 2026" for a UTC day. */
export function formatDayLong(day: Maybe<string>): string {
  if (!day) return DASH;
  const d = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return DASH;
  return new Intl.DateTimeFormat(LOCALE, { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(d);
}

/** The day of a timestamp in the viewer's zone, for axes spanning days: "21 Sept". */
export function formatDayOf(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", timeZone }).format(new Date(iso));
}

/** The hour of a UTC timestamp in the viewer's zone, for hourly charts: "14:00". */
export function formatHour(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit", timeZone }).format(new Date(iso));
}

/**
 * An email masked the way admin_users_v masks it: the first letter of the local part,
 * then ***@ and the domain ("s***@lincoln.edu"). Used to hide a revealed address again.
 */
export function maskEmail(email: Maybe<string>): string | null {
  if (!email) return null;
  const at = email.indexOf("@");
  if (at < 0) return null;
  return `${email.slice(0, 1)}***@${email.slice(at + 1)}`;
}

/** A child's username as the view masks it: "ava***". */
export function maskUsername(username: Maybe<string>): string | null {
  return username ? `${username.slice(0, 3)}***` : null;
}

export function ageBandLabel(band: Maybe<string>): string {
  switch (band) {
    case "under_13":
      return "Under 13";
    case "13_17":
      return "13 to 17";
    case "18_plus":
      return "18 and over";
    default:
      return "Unknown";
  }
}

const PROVIDERS: Record<string, string> = { google: "Google", microsoft: "Microsoft", saml: "SAML", password: "Password", pin: "Child PIN", desktop: "Desktop app" };

/** A sign-in or single sign-on provider as people write it: "SAML", not "Saml". */
export function providerLabel(value: Maybe<string>): string {
  if (!value) return DASH;
  return PROVIDERS[value] ?? humanize(value);
}

/** "waiting_on_us" → "Waiting on us"; "sign_in_failed" → "Sign in failed". */
export function humanize(value: Maybe<string>): string {
  if (!value) return DASH;
  const text = value.replace(/[_.]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function percent(part: number, whole: number): string {
  if (!whole) return DASH;
  const p = (part / whole) * 100;
  return `${p < 10 ? oneDecimal.format(p) : integer.format(p)}%`;
}

/** A ticket's number from its id, as students see it: 42 → "AN-0042". */
export function ticketNumber(id: number): string {
  return `AN-${String(id).padStart(4, "0")}`;
}

/** "AN-0042", "an-42" or "42" → 42; anything else → null. */
export function ticketIdFromNumber(value: string): number | null {
  const match = /^(?:an-)?0*(\d{1,9})$/i.exec(value.trim());
  return match ? Number(match[1]) : null;
}
