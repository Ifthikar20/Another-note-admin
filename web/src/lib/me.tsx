/** Who is signed in (GET /bff/me), and what their role lets them do. */
import { createContext, useContext } from "react";

import type { Me } from "./types";

export const MeContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(MeContext);
  if (!me) throw new Error("useMe outside MeContext");
  return me;
}

/** Whether the signed-in role has a capability (bff/app/members.py CAPABILITIES). */
export function useCan(capability: string): boolean {
  const me = useContext(MeContext);
  return !!me && me.capabilities.includes(capability);
}
