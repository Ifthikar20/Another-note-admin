/**
 * App-wide session states that replace the whole screen: the Cloudflare Access session
 * ended (a /bff call was redirected to sign-in, or answered 401), or the screen locked
 * after inactivity. A tiny store, read with useSyncExternalStore.
 */
import { useSyncExternalStore } from "react";

export type SessionState = "active" | "ended" | "locked";

let state: SessionState = "active";
const listeners = new Set<() => void>();

function set(next: SessionState) {
  if (state === next) return;
  // An ended session stays ended: only a reload (through Cloudflare Access) starts again.
  if (state === "ended") return;
  state = next;
  listeners.forEach((l) => l());
}

export const session = {
  get: () => state,
  end: () => set("ended"),
  lock: () => set("locked"),
  unlock: () => {
    if (state === "locked") {
      state = "active";
      listeners.forEach((l) => l());
    }
  },
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  /** Tests only. */
  reset: () => {
    state = "active";
    listeners.forEach((l) => l());
  },
};

export function useSessionState(): SessionState {
  return useSyncExternalStore(session.subscribe, session.get, session.get);
}
