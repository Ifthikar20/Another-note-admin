/**
 * The frame of every page: the amber ADMIN strip across the top (so this is never
 * mistaken for the student app), the navigation (only what the role may use), and the
 * page itself.
 */
import {
  Activity,
  Building2,
  Coins,
  Inbox,
  LayoutDashboard,
  Layers,
  LogOut,
  Menu,
  Moon,
  ScrollText,
  Settings,
  ShieldAlert,
  Sun,
  Users,
} from "lucide-react";
import { useState, type ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useLiveTickets } from "@/lib/live";
import { useMe } from "@/lib/me";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

import { RoleBadge } from "./badges";

export interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  capability: string;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: LayoutDashboard, capability: "metrics.read" },
  { to: "/users", label: "Users", icon: Users, capability: "users.read" },
  { to: "/tickets", label: "Tickets", icon: Inbox, capability: "tickets.read" },
  { to: "/activity", label: "Activity", icon: Activity, capability: "metrics.read" },
  { to: "/usage", label: "Usage and cost", icon: Coins, capability: "metrics.read" },
  { to: "/plans", label: "Plans", icon: Layers, capability: "plans.read" },
  { to: "/orgs", label: "Organisations", icon: Building2, capability: "orgs.read" },
  { to: "/security", label: "Security", icon: ShieldAlert, capability: "security.read" },
  { to: "/audit", label: "Audit log", icon: ScrollText, capability: "audit.read" },
  { to: "/settings", label: "Settings", icon: Settings, capability: "settings.read" },
];

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const me = useMe();
  const { unread, enabled } = useLiveTickets();
  return (
    <nav aria-label="Admin sections" className="space-y-0.5 p-2">
      {NAV.filter((item) => me.capabilities.includes(item.capability)).map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
              isActive ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground" : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
            )
          }
        >
          <item.icon className="size-4 shrink-0" />
          <span className="flex-1">{item.label}</span>
          {item.to === "/tickets" && enabled && unread.size > 0 ? (
            <span className="num rounded-full bg-strip px-1.5 text-[11px] font-semibold text-strip-foreground" aria-label={`${unread.size} unread`}>
              {unread.size > 99 ? "99+" : unread.size}
            </span>
          ) : null}
        </NavLink>
      ))}
    </nav>
  );
}

function Strip() {
  const me = useMe();
  const theme = useTheme();
  const [menu, setMenu] = useState(false);
  return (
    <header className="sticky top-0 z-40 flex h-9 items-center gap-3 bg-strip px-3 text-strip-foreground">
      <Sheet open={menu} onOpenChange={setMenu}>
        <SheetTrigger asChild>
          <button type="button" className="rounded p-1 hover:bg-black/10 md:hidden" aria-label="Open the menu">
            <Menu className="size-4" />
          </button>
        </SheetTrigger>
        <SheetContent side="left" className="w-64 p-0">
          <SheetTitle className="px-4 pt-4 text-sm">AnotherNote Admin</SheetTitle>
          <Nav onNavigate={() => setMenu(false)} />
        </SheetContent>
      </Sheet>
      <span className="text-[11px] font-bold tracking-[0.14em]">ANOTHERNOTE ADMIN</span>
      <span className="hidden text-[12px] opacity-80 sm:inline">Staff only · never shows study content</span>
      {me.environment !== "production" ? (
        <span className="rounded bg-black/15 px-1.5 text-[11px] font-semibold uppercase tracking-wide">{me.environment}</span>
      ) : null}
      <div className="ml-auto flex items-center gap-2 text-[12px]">
        <span className="hidden truncate sm:inline" title={me.dev_identity ? "Development identity: this machine only" : "Signed in through Cloudflare Access"}>
          {me.email}
        </span>
        <RoleBadge role={me.role} />
        <button type="button" onClick={theme.toggle} className="rounded p-1 hover:bg-black/10" aria-label={theme.isDark ? "Use the light theme" : "Use the dark theme"}>
          {theme.isDark ? <Moon className="size-4" /> : <Sun className="size-4" />}
        </button>
        {me.sign_out_url ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-strip-foreground hover:bg-black/10 hover:text-strip-foreground"
            onClick={() => window.location.assign(me.sign_out_url as string)}
          >
            <LogOut /> Sign out
          </Button>
        ) : null}
      </div>
    </header>
  );
}

export function AppShell() {
  return (
    <div className="min-h-screen bg-background">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-10 focus:z-50 focus:rounded focus:bg-background focus:px-3 focus:py-2">
        Skip to content
      </a>
      <Strip />
      <div className="flex">
        <aside className="sticky top-9 hidden h-[calc(100vh-2.25rem)] w-56 shrink-0 overflow-y-auto border-r bg-sidebar md:block">
          <Nav />
        </aside>
        <main id="main" className="min-w-0 flex-1 px-4 py-5 md:px-6 lg:px-8">
          <div className="mx-auto max-w-[1400px]">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
