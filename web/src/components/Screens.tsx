/** Whole-screen states: signing in, not a member, session ended, locked, and "can't reach it". */
import { Lock, LogIn, ShieldX, WifiOff } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";

function Frame({ icon, title, children, action }: { icon: ReactNode; title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="h-7 bg-strip" aria-hidden />
      <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-6 py-16">
        <p className="text-[11px] font-bold tracking-[0.12em] text-[hsl(38_92%_32%)] dark:text-strip">ANOTHERNOTE ADMIN</p>
        <div className="mt-4 flex items-center gap-2">
          {icon}
          <h1 className="text-lg font-semibold">{title}</h1>
        </div>
        <div className="mt-2 space-y-2 text-[13px] text-muted-foreground">{children}</div>
        {action ? <div className="mt-5">{action}</div> : null}
      </main>
    </div>
  );
}

export function Splash() {
  return (
    <Frame icon={<LogIn className="size-5 text-muted-foreground" />} title="Checking who you are…">
      <p>One moment.</p>
    </Frame>
  );
}

export function SessionEndedScreen() {
  return (
    <Frame
      icon={<LogIn className="size-5 text-muted-foreground" />}
      title="Your session ended"
      action={<Button onClick={() => window.location.reload()}>Sign in again</Button>}
    >
      <p>Your Cloudflare Access sign-in has expired or was signed out. Sign in again to carry on; nothing you were looking at was kept.</p>
    </Frame>
  );
}

export function NotMemberScreen() {
  return (
    <Frame icon={<ShieldX className="size-5 text-destructive" />} title="You're not on the admin list">
      <p>You signed in, but your account is not one of this app's admin members.</p>
      <p>If you should have access, ask the owner to add you. Access needs two things: the Cloudflare Access policy and the admin member list.</p>
    </Frame>
  );
}

export function BootErrorScreen({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Frame icon={<WifiOff className="size-5 text-destructive" />} title="The admin app isn't answering" action={<Button onClick={onRetry}>Try again</Button>}>
      <p>{message}</p>
    </Frame>
  );
}

export function LockScreen({ minutes, onContinue, signOutMinutes }: { minutes: number; onContinue: () => void; signOutMinutes: number }) {
  return (
    <Frame icon={<Lock className="size-5 text-muted-foreground" />} title="Locked while you were away" action={<Button onClick={onContinue} autoFocus>Continue</Button>}>
      <p>
        The screen locked after {minutes} minutes without activity, and the data it showed was cleared from this tab. Continue to load it again.
      </p>
      <p>After {signOutMinutes} minutes without activity you are signed out, and signing in again needs Cloudflare Access.</p>
    </Frame>
  );
}
