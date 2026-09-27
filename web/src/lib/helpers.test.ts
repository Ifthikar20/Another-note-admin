import { describe, expect, it } from "vitest";

import { parseSse } from "./live";
import { pivot, present, tableOf } from "./pivot";
import { addDays, daysBetween, parseRange, presetRange, rangeLabel } from "./range";
import { fillReply, SAVED_REPLIES } from "./savedReplies";
import { METHODS } from "./series";

describe("the event stream parser", () => {
  it("splits whole events and keeps the rest for the next chunk", () => {
    const { events, rest } = parseSse(': ping\n\nid: 7\nevent: ticket.created\ndata: {"id":7}\n\nevent: ticket.user_replied\r\ndata: {"id":8}\r\n\r\nevent: ticket.cre');
    expect(events).toEqual([
      { event: "ticket.created", data: '{"id":7}' },
      { event: "ticket.user_replied", data: '{"id":8}' },
    ]);
    expect(rest).toBe("event: ticket.cre");
  });
});

describe("date ranges", () => {
  const now = new Date("2026-10-31T23:30:00Z");

  it("computes presets in UTC days", () => {
    expect(presetRange("today", now)).toEqual({ from: "2026-10-31", to: "2026-10-31" });
    expect(presetRange("7d", now)).toEqual({ from: "2026-10-25", to: "2026-10-31" });
    expect(presetRange("30d", now)).toEqual({ from: "2026-10-02", to: "2026-10-31" });
    expect(presetRange("mtd", now)).toEqual({ from: "2026-10-01", to: "2026-10-31" });
  });

  it("reads a range from the URL, and ignores a bad one", () => {
    expect(parseRange(new URLSearchParams("from=2026-10-01&to=2026-10-05"), "30d", now)).toEqual({ from: "2026-10-01", to: "2026-10-05", preset: "custom" });
    expect(parseRange(new URLSearchParams("from=2026-10-05&to=2026-10-01"), "7d", now).preset).toBe("7d");
    expect(parseRange(new URLSearchParams("range=90d"), "30d", now).from).toBe("2026-08-03");
    expect(parseRange(new URLSearchParams("range=bogus"), "30d", now).preset).toBe("30d");
  });

  it("lists days and labels ranges", () => {
    expect(daysBetween("2026-10-30", "2026-11-01")).toEqual(["2026-10-30", "2026-10-31", "2026-11-01"]);
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(rangeLabel({ from: "2026-10-01", to: "2026-10-31" })).toBe("1 Oct – 31 Oct 2026");
    expect(rangeLabel({ from: "2025-12-30", to: "2026-01-02" })).toBe("30 Dec 2025 – 2 Jan 2026");
    expect(rangeLabel({ from: "2026-10-31", to: "2026-10-31" })).toBe("31 Oct 2026");
  });
});

describe("chart rows", () => {
  it("pivots long rows into one row per day, folding keys", () => {
    const rows = pivot(
      ["2026-10-01", "2026-10-02"],
      [
        { day: "2026-10-01", key: "google", value: 3 },
        { day: "2026-10-01", key: "password", value: 2 },
        { day: "2026-10-02", key: "google", value: 1 },
        { day: "2026-10-03", key: "google", value: 99 },
      ],
    );
    expect(rows).toEqual([
      { day: "2026-10-01", google: 3, password: 2 },
      { day: "2026-10-02", google: 1 },
    ]);
    expect(present(METHODS, rows).map((s) => s.key)).toEqual(["password", "google"]);
    expect(tableOf(rows, present(METHODS, rows), String)).toEqual({
      columns: ["Day (UTC)", "Password", "Google", "Total"],
      rows: [
        ["1 Oct", "2", "3", "5"],
        ["2 Oct", "0", "1", "1"],
      ],
    });
  });
});

describe("saved replies", () => {
  it("fills the first name and the ticket number, with a fallback", () => {
    const closing = SAVED_REPLIES.find((r) => r.id === "closing")!;
    expect(fillReply(closing.body, { first_name: "Sam", number: "AN-0042" })).toContain("Hi Sam,");
    expect(fillReply(closing.body, { first_name: "Sam", number: "AN-0042" })).toContain("closing AN-0042");
    expect(fillReply("Hi {first_name}", { first_name: "  " })).toBe("Hi there");
  });
});
