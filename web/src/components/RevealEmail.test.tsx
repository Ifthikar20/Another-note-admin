import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { MeContext } from "@/lib/me";
import type { Role } from "@/lib/types";
import { fakeFetch, me } from "@/test/fixtures";

import { RevealEmail } from "./RevealEmail";

function renderReveal(role: Role, masked: string | null = "s***@lincoln.edu") {
  const fake = fakeFetch({ "POST /bff/users/481/reveal-email": { email: "sam.okafor@lincoln.edu", first_name: "Sam" } });
  vi.stubGlobal("fetch", fake.fn);
  render(
    <MeContext.Provider value={me(role)}>
      <TooltipProvider>
        <RevealEmail userId={481} masked={masked} />
      </TooltipProvider>
    </MeContext.Provider>,
  );
  return fake.calls;
}

describe("revealing an email", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("asks why, shows the address for 60 seconds, then masks it again", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const calls = renderReveal("support");
    expect(screen.getByTestId("email")).toHaveTextContent("s***@lincoln.edu");

    await user.click(screen.getByRole("button", { name: "Reveal" }));
    const submit = screen.getByRole("button", { name: "Reveal" });
    await user.type(screen.getByLabelText("Reason"), "why");
    expect(submit).toBeDisabled(); // at least five characters
    await user.type(screen.getByLabelText("Reason"), " - replying to their ticket by email");
    await user.type(screen.getByLabelText("Ticket (optional)"), "AN-0042");
    await user.click(submit);

    expect(await screen.findByText("sam.okafor@lincoln.edu")).toBeInTheDocument();
    expect(calls).toHaveLength(1);
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ reason: "why - replying to their ticket by email", ticket_id: 42 });
    expect((calls[0].init?.headers as Record<string, string>)["X-Requested-With"]).toBe("admin");
    expect(screen.getByText(/Hides in 60 s/)).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(58_000));
    expect(screen.getByTestId("email")).toHaveTextContent("sam.okafor@lincoln.edu");
    act(() => vi.advanceTimersByTime(3_000));
    expect(screen.getByTestId("email")).toHaveTextContent("s***@lincoln.edu");
    expect(screen.queryByText("sam.okafor@lincoln.edu")).not.toBeInTheDocument();
  });

  it("can be hidden again at once", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderReveal("owner");
    await user.click(screen.getByRole("button", { name: "Reveal" }));
    await user.type(screen.getByLabelText("Reason"), "Guardian asked us to confirm the account");
    await user.click(screen.getByRole("button", { name: "Reveal" }));
    await screen.findByText("sam.okafor@lincoln.edu");
    await user.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.getByTestId("email")).toHaveTextContent("s***@lincoln.edu");
  });

  it("refuses a ticket that isn't a ticket number", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderReveal("support");
    await user.click(screen.getByRole("button", { name: "Reveal" }));
    await user.type(screen.getByLabelText("Reason"), "Replying to their ticket");
    await user.type(screen.getByLabelText("Ticket (optional)"), "the one from yesterday");
    expect(screen.getByText("A ticket number looks like AN-0042.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reveal" })).toBeDisabled();
  });

  it.each(["analyst", "viewer"] as const)("offers no Reveal to %s", (role) => {
    renderReveal(role);
    expect(screen.getByTestId("email")).toHaveTextContent("s***@lincoln.edu");
    expect(screen.queryByRole("button", { name: "Reveal" })).not.toBeInTheDocument();
  });

  it("has nothing to reveal for a child profile", () => {
    renderReveal("owner", null);
    expect(screen.getByText("No email (child profile)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reveal" })).not.toBeInTheDocument();
  });
});
