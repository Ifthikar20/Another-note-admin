/**
 * The app: who is signed in (GET /bff/me) decides everything else. Until that answers,
 * nothing else is fetched; a 403 means "not an admin member", a 401 or a redirect means
 * the Cloudflare Access session ended.
 */
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router-dom";

import { useIdleLock } from "@/components/IdleLock";
import { BootErrorScreen, LockScreen, NotMemberScreen, SessionEndedScreen, Splash } from "@/components/Screens";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError, api, errorMessage } from "@/lib/api";
import { LiveTicketsProvider } from "@/lib/live";
import { MeContext } from "@/lib/me";
import { useSessionState } from "@/lib/session";
import type { Me } from "@/lib/types";

import { router } from "./routes";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // A refused or missing thing won't change by asking again.
        retry: (count, error) => !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
    },
  });
}

function Signed({ me }: { me: Me }) {
  const state = useSessionState();
  const idle = useIdleLock({ lockMinutes: me.idle_lock_minutes, signOutMinutes: me.idle_sign_out_minutes, signOutUrl: me.sign_out_url });
  if (state === "locked") {
    return <LockScreen minutes={me.idle_lock_minutes} signOutMinutes={me.idle_sign_out_minutes} onContinue={idle.unlock} />;
  }
  return (
    <>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
      <Toaster position="bottom-right" closeButton />
    </>
  );
}

function Boot() {
  const state = useSessionState();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me"), staleTime: Infinity, retry: false });
  if (state === "ended") return <SessionEndedScreen />;
  if (me.isPending) return <Splash />;
  if (me.isError) {
    if (me.error instanceof ApiError && me.error.status === 403) return <NotMemberScreen />;
    return <BootErrorScreen message={errorMessage(me.error)} onRetry={() => void me.refetch()} />;
  }
  return (
    <MeContext.Provider value={me.data}>
      <LiveTicketsProvider>
        <Signed me={me.data} />
      </LiveTicketsProvider>
    </MeContext.Provider>
  );
}

export function App() {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={300}>
        <Boot />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
