/**
 * Inactivity: after `lockMinutes` without a key, click, touch or scroll, the screen locks
 * and every cached admin answer is dropped from memory; after `signOutMinutes` the
 * Cloudflare Access session is ended, so coming back needs single sign-on and MFA again.
 * Time is measured with the wall clock, so a laptop that slept is judged on waking.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { session } from "@/lib/session";

const EVENTS = ["pointerdown", "keydown", "wheel", "touchstart", "mousemove"] as const;

export function useIdleLock({ lockMinutes, signOutMinutes, signOutUrl }: { lockMinutes: number; signOutMinutes: number; signOutUrl: string | null }) {
  const queryClient = useQueryClient();
  const last = useRef(Date.now());

  useEffect(() => {
    const touch = () => {
      if (session.get() === "active") last.current = Date.now();
    };
    let lastMove = 0;
    const onMove = () => {
      const t = Date.now();
      if (t - lastMove > 5000) {
        lastMove = t;
        touch();
      }
    };
    for (const e of EVENTS) window.addEventListener(e, e === "mousemove" ? onMove : touch, { passive: true });

    const check = () => {
      const idle = Date.now() - last.current;
      if (signOutUrl && idle >= signOutMinutes * 60_000) {
        queryClient.clear();
        window.location.assign(signOutUrl);
        return;
      }
      if (session.get() === "active" && idle >= lockMinutes * 60_000) {
        // Drop everything the screen showed; only "who am I" survives the lock.
        queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
        session.lock();
      }
    };
    const timer = setInterval(check, 15_000);
    const onVisible = () => {
      if (document.visibilityState === "visible") check();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      for (const e of EVENTS) window.removeEventListener(e, e === "mousemove" ? onMove : touch);
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [lockMinutes, signOutMinutes, signOutUrl, queryClient]);

  return {
    unlock: () => {
      last.current = Date.now();
      session.unlock();
    },
  };
}
