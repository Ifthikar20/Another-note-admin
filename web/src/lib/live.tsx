/**
 * Live ticket events for the unread badge (spec 5.5.3): new tickets and replies from
 * students, as they happen.
 *
 * The stream is read with fetch rather than EventSource, because every /bff call must
 * carry X-Requested-With: admin and EventSource cannot send headers. On (re)connect it
 * catches up from the last event it saw, then follows; it backs off after errors.
 * Unread tickets are kept per browser (localStorage), across tabs.
 */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { BASE_HEADERS, api } from "./api";
import { ticketNumber } from "./format";
import { useCan } from "./me";
import { session } from "./session";
import type { OutboxEvent } from "./types";

const UNREAD_KEY = "admin.tickets.unread";
const CURSOR_KEY = "admin.tickets.cursor";

interface LiveTickets {
  unread: ReadonlySet<number>;
  connected: boolean;
  enabled: boolean;
  markRead: (ticketId: number) => void;
  markAllRead: () => void;
}

const LiveContext = createContext<LiveTickets>({
  unread: new Set(),
  connected: false,
  enabled: false,
  markRead: () => undefined,
  markAllRead: () => undefined,
});

function readUnread(): Set<number> {
  try {
    const raw = JSON.parse(localStorage.getItem(UNREAD_KEY) ?? "[]");
    return new Set(Array.isArray(raw) ? raw.filter((n) => Number.isInteger(n)).slice(-200) : []);
  } catch {
    return new Set();
  }
}

function writeUnread(set: Set<number>) {
  try {
    localStorage.setItem(UNREAD_KEY, JSON.stringify([...set].slice(-200)));
  } catch {
    /* blocked storage: unread lasts this page only */
  }
}

function readCursor(): number | null {
  try {
    const v = Number(localStorage.getItem(CURSOR_KEY));
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

function writeCursor(id: number) {
  try {
    localStorage.setItem(CURSOR_KEY, String(id));
  } catch {
    /* ignore */
  }
}

/** Server-sent events from a text stream, split into (event, data) pairs. */
export function parseSse(buffer: string): { events: { event: string; data: string }[]; rest: string } {
  const normalized = buffer.replace(/\r\n?/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (data.length) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

export function LiveTicketsProvider({ children }: { children: ReactNode }) {
  const enabled = useCan("tickets.events");
  const queryClient = useQueryClient();
  const [unread, setUnread] = useState<Set<number>>(readUnread);
  const [connected, setConnected] = useState(false);
  const cursor = useRef<number | null>(readCursor());

  const apply = useCallback(
    (events: OutboxEvent[], announce: boolean) => {
      if (!events.length) return;
      setUnread((current) => {
        const next = new Set(current);
        for (const e of events) next.add(e.ticket_id);
        writeUnread(next);
        return next;
      });
      const last = Math.max(...events.map((e) => e.id));
      cursor.current = Math.max(cursor.current ?? 0, last);
      writeCursor(cursor.current);
      void queryClient.invalidateQueries({ queryKey: ["tickets"] });
      for (const e of events) void queryClient.invalidateQueries({ queryKey: ["ticket", e.ticket_id] });
      if (announce) {
        for (const e of events.slice(-3)) {
          toast(e.kind === "ticket.created" ? `New ticket ${ticketNumber(e.ticket_id)}` : `New reply on ${ticketNumber(e.ticket_id)}`, {
            action: { label: "Open", onClick: () => window.location.assign(`/tickets/${ticketNumber(e.ticket_id)}`) },
          });
        }
      }
    },
    [queryClient],
  );

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let controller: AbortController | null = null;
    let backoff = 1000;

    const run = async () => {
      try {
        if (cursor.current === null) {
          // First visit from this browser: start from now, nothing is unread yet.
          const latest = await api.get<{ items: OutboxEvent[] }>("/events", { limit: 1 });
          cursor.current = latest.items.at(-1)?.id ?? 0;
          writeCursor(cursor.current);
        } else {
          const missed = await api.get<{ items: OutboxEvent[] }>("/events", { after: cursor.current, limit: 100 });
          apply(missed.items, false);
        }
      } catch {
        /* the stream below retries */
      }
      while (!stopped) {
        controller = new AbortController();
        try {
          const res = await fetch(`/bff/events/stream?after=${cursor.current ?? 0}`, {
            headers: { ...BASE_HEADERS, Accept: "text/event-stream" },
            credentials: "same-origin",
            redirect: "manual",
            cache: "no-store",
            signal: controller.signal,
          });
          if (res.type === "opaqueredirect" || res.status === 401) {
            session.end();
            return;
          }
          if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
          setConnected(true);
          backoff = 1000;
          const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
          let buffer = "";
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += value;
            const { events, rest } = parseSse(buffer);
            buffer = rest;
            const parsed: OutboxEvent[] = [];
            for (const e of events) {
              try {
                const data = JSON.parse(e.data) as OutboxEvent;
                if (data && typeof data.ticket_id === "number") parsed.push(data);
              } catch {
                /* not ours */
              }
            }
            apply(parsed, true);
          }
        } catch (e) {
          if (stopped || (e instanceof DOMException && e.name === "AbortError")) return;
        }
        setConnected(false);
        await new Promise((r) => setTimeout(r, backoff));
        backoff = Math.min(backoff * 2, 30_000);
      }
    };
    void run();

    const onStorage = (e: StorageEvent) => {
      if (e.key === UNREAD_KEY) setUnread(readUnread());
    };
    window.addEventListener("storage", onStorage);
    return () => {
      stopped = true;
      controller?.abort();
      setConnected(false);
      window.removeEventListener("storage", onStorage);
    };
  }, [enabled, apply]);

  const markRead = useCallback((ticketId: number) => {
    setUnread((current) => {
      if (!current.has(ticketId)) return current;
      const next = new Set(current);
      next.delete(ticketId);
      writeUnread(next);
      return next;
    });
  }, []);

  const markAllRead = useCallback(() => {
    const next = new Set<number>();
    writeUnread(next);
    setUnread(next);
  }, []);

  const value = useMemo(() => ({ unread, connected, enabled, markRead, markAllRead }), [unread, connected, enabled, markRead, markAllRead]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useLiveTickets(): LiveTickets {
  return useContext(LiveContext);
}
