import { describe, expect, it } from "vitest";

import {
  ageBandLabel,
  formatAudioMinutes,
  formatBytes,
  formatCompact,
  formatDateTime,
  formatDay,
  formatDuration,
  formatHours,
  formatInt,
  formatMoney,
  formatMoneyCompact,
  formatRelative,
  humanize,
  maskEmail,
  maskUsername,
  providerLabel,
  ticketIdFromNumber,
  ticketNumber,
} from "./format";

describe("numbers", () => {
  it("separates thousands and rounds", () => {
    expect(formatInt(1284)).toBe("1,284");
    expect(formatInt(18234000.4)).toBe("18,234,000");
    expect(formatInt(null)).toBe("—");
    expect(formatInt(Number.NaN)).toBe("—");
  });

  it("compacts large numbers for tiles and axes", () => {
    expect(formatCompact(9_999)).toBe("9,999");
    expect(formatCompact(12_900)).toBe("12.9K");
    expect(formatCompact(18_234_000)).toBe("18.2M");
    expect(formatCompact(1_300_000_000)).toBe("1.3B");
    expect(formatCompact(undefined)).toBe("—");
  });
});

describe("money", () => {
  it("is dollars to two decimals, and an unknown price is a dash, never $0.00", () => {
    expect(formatMoney(41.27)).toBe("$41.27");
    expect(formatMoney(903.123)).toBe("$903.12");
    expect(formatMoney(0)).toBe("$0.00");
    expect(formatMoney(0.001)).toBe("<$0.01");
    expect(formatMoney(null)).toBe("—");
  });

  it("compacts only large sums", () => {
    expect(formatMoneyCompact(903.12)).toBe("$903.12");
    expect(formatMoneyCompact(15_300)).toBe("$15.3K");
  });
});

describe("sizes and durations", () => {
  it("writes bytes in decimal units", () => {
    expect(formatBytes(999)).toBe("999 B");
    expect(formatBytes(81_233_455)).toBe("81.2 MB");
    expect(formatBytes(18_233_455_112)).toBe("18.2 GB");
  });

  it("writes durations from seconds", () => {
    expect(formatDuration(45)).toBe("45 s");
    expect(formatDuration(720)).toBe("12 min");
    expect(formatDuration(3900)).toBe("1 h 5 min");
    expect(formatDuration(7200)).toBe("2 h");
    expect(formatDuration(97200)).toBe("1 d 3 h");
  });

  it("writes audio minutes and ages in hours", () => {
    expect(formatAudioMinutes(750_000)).toBe("12.5 min");
    expect(formatHours(0.5)).toBe("30 min");
    expect(formatHours(20.5)).toBe("20.5 h");
    expect(formatHours(72)).toBe("3 d");
  });
});

describe("times", () => {
  const now = Date.parse("2026-10-31T14:05:00Z");

  it("says how long ago, or how soon", () => {
    expect(formatRelative("2026-10-31T14:04:40Z", now)).toBe("just now");
    expect(formatRelative("2026-10-31T13:55:00Z", now)).toBe("10 minutes ago");
    expect(formatRelative("2026-10-31T11:05:00Z", now)).toBe("3 hours ago");
    expect(formatRelative("2026-10-30T14:05:00Z", now)).toBe("yesterday");
    expect(formatRelative("2026-10-28T14:05:00Z", now)).toBe("3 days ago");
    expect(formatRelative("2026-11-01T14:05:00Z", now)).toBe("tomorrow");
    expect(formatRelative("2026-10-31T11:05:00Z", now, "short")).toBe("3 hr. ago");
    expect(formatRelative(null, now)).toBe("—");
  });

  it("shows the exact moment in the viewer's time zone", () => {
    expect(formatDateTime("2026-10-31T14:05:09Z", "UTC")).toBe("31 Oct 2026, 14:05:09");
    expect(formatDateTime("2026-10-31T14:05:09Z", "Asia/Kolkata")).toBe("31 Oct 2026, 19:35:09");
  });

  it("keeps a UTC day the same day wherever the viewer is", () => {
    expect(formatDay("2026-10-31")).toBe("31 Oct");
  });
});

describe("identities", () => {
  it("masks an email the way admin_users_v does", () => {
    expect(maskEmail("sam.okafor@lincoln.edu")).toBe("s***@lincoln.edu");
    expect(maskEmail("x@y.z")).toBe("x***@y.z");
    expect(maskEmail(null)).toBeNull();
    expect(maskEmail("not an email")).toBeNull();
  });

  it("masks a child's username", () => {
    expect(maskUsername("ava-k3m9")).toBe("ava***");
    expect(maskUsername(null)).toBeNull();
  });

  it("shows an age band, never a year", () => {
    expect(ageBandLabel("under_13")).toBe("Under 13");
    expect(ageBandLabel("13_17")).toBe("13 to 17");
    expect(ageBandLabel("18_plus")).toBe("18 and over");
    expect(ageBandLabel("anything else")).toBe("Unknown");
  });
});

describe("labels and ticket numbers", () => {
  it("humanizes codes", () => {
    expect(humanize("waiting_on_us")).toBe("Waiting on us");
    expect(humanize("view.user")).toBe("View user");
    expect(providerLabel("saml")).toBe("SAML");
    expect(providerLabel("pin")).toBe("Child PIN");
  });

  it("round-trips ticket numbers", () => {
    expect(ticketNumber(42)).toBe("AN-0042");
    expect(ticketNumber(12345)).toBe("AN-12345");
    expect(ticketIdFromNumber("AN-0042")).toBe(42);
    expect(ticketIdFromNumber("an-42")).toBe(42);
    expect(ticketIdFromNumber(" 42 ")).toBe(42);
    expect(ticketIdFromNumber("AN-")).toBeNull();
    expect(ticketIdFromNumber("42; DROP")).toBeNull();
  });
});
