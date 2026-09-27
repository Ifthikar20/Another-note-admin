/**
 * A person as the admin app may show them: masked email (or a child's masked username),
 * and first name. Never more: revealing an address is a separate, audited action.
 */
import { Link } from "react-router-dom";

import type { Identity as IdentityT, Kind } from "@/lib/types";
import { cn } from "@/lib/utils";

import { Pill } from "./badges";

export function identityText(identity: IdentityT): string {
  return identity.email_masked ?? identity.username_masked ?? "No email";
}

export function Identity({
  id,
  identity,
  kind,
  link = true,
  className,
}: {
  id: number;
  identity: IdentityT;
  kind?: Kind;
  link?: boolean;
  className?: string;
}) {
  const main = identityText(identity);
  const content = (
    <span className={cn("inline-flex min-w-0 items-center gap-1.5", className)}>
      <span className="truncate font-medium">{main}</span>
      {identity.first_name ? <span className="truncate text-muted-foreground">{identity.first_name}</span> : null}
      {kind === "managed_child" ? <Pill variant="accent">Child</Pill> : null}
    </span>
  );
  if (!link) return content;
  return (
    <Link to={`/users/${id}`} className="min-w-0 hover:underline" onClick={(e) => e.stopPropagation()}>
      {content}
    </Link>
  );
}

export function UserLink({ id }: { id: number | null }) {
  if (!id) return <span className="text-muted-foreground">Signed out</span>;
  return (
    <Link to={`/users/${id}`} className="num hover:underline" onClick={(e) => e.stopPropagation()}>
      #{id}
    </Link>
  );
}
