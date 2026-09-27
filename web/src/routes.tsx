/** Every page, and the capability it needs (the BFF and the admin API check again). */
import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Link } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { LoadingBlock } from "@/components/states";
import { useCan } from "@/lib/me";

const Overview = lazy(() => import("@/pages/Overview"));
const Users = lazy(() => import("@/pages/Users"));
const UserDetail = lazy(() => import("@/pages/UserDetail"));
const Tickets = lazy(() => import("@/pages/Tickets"));
const TicketDetail = lazy(() => import("@/pages/TicketDetail"));
const ActivityPage = lazy(() => import("@/pages/Activity"));
const Usage = lazy(() => import("@/pages/Usage"));
const Plans = lazy(() => import("@/pages/Plans"));
const Orgs = lazy(() => import("@/pages/Orgs"));
const Security = lazy(() => import("@/pages/Security"));
const Audit = lazy(() => import("@/pages/Audit"));
const SettingsPage = lazy(() => import("@/pages/Settings"));

export function Forbidden() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-lg font-semibold">Your role can't open this page</h1>
      <p className="mt-1 text-[13px] text-muted-foreground">Ask the owner if you need it.</p>
      <Link to="/" className="mt-4 inline-block text-[13px] underline">
        Back to the overview
      </Link>
    </div>
  );
}

function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-lg font-semibold">There's no page here</h1>
      <Link to="/" className="mt-4 inline-block text-[13px] underline">
        Back to the overview
      </Link>
    </div>
  );
}

function Guard({ need, children }: { need: string; children: ReactNode }) {
  const allowed = useCan(need);
  if (!allowed) return <Forbidden />;
  return <Suspense fallback={<LoadingBlock rows={8} />}>{children}</Suspense>;
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { path: "/", element: <Guard need="metrics.read"><Overview /></Guard> },
      { path: "/users", element: <Guard need="users.read"><Users /></Guard> },
      { path: "/users/:id", element: <Guard need="users.read"><UserDetail /></Guard> },
      { path: "/tickets", element: <Guard need="tickets.read"><Tickets /></Guard> },
      { path: "/tickets/:number", element: <Guard need="tickets.read"><TicketDetail /></Guard> },
      { path: "/activity", element: <Guard need="metrics.read"><ActivityPage /></Guard> },
      { path: "/usage", element: <Guard need="metrics.read"><Usage /></Guard> },
      { path: "/plans", element: <Guard need="plans.read"><Plans /></Guard> },
      { path: "/orgs", element: <Guard need="orgs.read"><Orgs /></Guard> },
      { path: "/security", element: <Guard need="security.read"><Security /></Guard> },
      { path: "/audit", element: <Guard need="audit.read"><Audit /></Guard> },
      { path: "/settings", element: <Guard need="settings.read"><SettingsPage /></Guard> },
      { path: "*", element: <NotFound /> },
    ],
  },
], {
  future: {
    v7_relativeSplatPath: true,
    v7_fetcherPersist: true,
    v7_normalizeFormMethod: true,
    v7_partialHydration: true,
    v7_skipActionErrorRevalidation: true,
  },
});
