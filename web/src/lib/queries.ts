/** Queries more than one page uses. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "./api";
import type { OrgRow, Page, Plan } from "./types";

export function usePlans() {
  return useQuery({ queryKey: ["plans"], queryFn: () => api.get<{ items: Plan[] }>("/plans"), staleTime: 60_000 });
}

export function useOrgOptions() {
  return useQuery({
    queryKey: ["orgs", "options"],
    queryFn: () => api.get<Page<OrgRow>>("/orgs", { limit: 100 }),
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });
}
