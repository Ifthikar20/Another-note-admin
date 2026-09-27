/**
 * The admin app end to end: every page of section 6.4 (and Activity) loads with data and
 * without console errors; the reveal, reply, live badge and idle lock work; and the
 * served app carries the security headers of section 6.6.
 */
import { expect, test, type Page } from "@playwright/test";

const PAGES: [string, string][] = [
  ["/", "Overview"],
  ["/users", "Users"],
  ["/users/5", "#5"],
  ["/users/5?tab=usage", "#5"],
  ["/users/5?tab=security", "#5"],
  ["/users/5?tab=app", "#5"],
  ["/tickets", "Tickets"],
  ["/tickets/AN-0003", "AN-0003"],
  ["/activity", "Activity"],
  ["/activity?tab=errors", "Activity"],
  ["/activity?tab=log", "Activity"],
  ["/usage", "Usage and cost"],
  ["/usage?group=day", "Usage and cost"],
  ["/plans", "Plans"],
  ["/orgs", "Organisations"],
  ["/security", "Security"],
  ["/audit", "Audit log"],
  ["/settings", "Settings"],
];

function watchConsole(page: Page): string[] {
  const problems: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") problems.push(m.text());
  });
  page.on("pageerror", (e) => problems.push(e.message));
  return problems;
}

async function settled(page: Page) {
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(page.locator('[aria-busy="true"]')).toHaveCount(0);
}

for (const [path, heading] of PAGES) {
  test(`${path} loads`, async ({ page }) => {
    const problems = watchConsole(page);
    await page.goto(path);
    await settled(page);
    await expect(page.locator("main")).toContainText(heading);
    await expect(page.getByRole("alert").filter({ hasText: "didn't load" })).toHaveCount(0);
    const text = await page.locator("body").innerText();
    expect(text).not.toContain("CANARY");
    expect(problems).toEqual([]);
  });
}

test("an unknown page says so", async ({ page }) => {
  await page.goto("/nowhere");
  await expect(page.getByText("There's no page here")).toBeVisible();
});

test("revealing an email is shown for 60 seconds, then masked again", async ({ page }) => {
  await page.clock.install();
  await page.goto("/users/5");
  await settled(page);
  const email = page.getByTestId("email");
  const masked = await email.innerText();
  expect(masked).toContain("***@");
  await page.getByRole("button", { name: "Reveal" }).click();
  await page.getByLabel("Reason").fill("Replying to their ticket by email");
  await page.getByRole("dialog").getByRole("button", { name: "Reveal" }).click();
  await expect(email).not.toContainText("***");
  await expect(page.getByText(/Hides in \d+ s/)).toBeVisible();
  await page.clock.fastForward(61_000);
  await expect(email).toHaveText(masked);
});

test("tickets: J moves, Enter opens, R starts a reply, and the reply is sent", async ({ page }) => {
  await page.goto("/tickets?queue=waiting_on_us");
  await settled(page);
  await page.keyboard.press("j");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/tickets\/AN-\d+/);
  await settled(page);
  await page.keyboard.press("r");
  const box = page.getByLabel(/Reply to/);
  await expect(box).toBeFocused();
  await box.fill("Thanks for waiting. We've found the problem and a fix is on its way.");
  await page.keyboard.press("Control+Enter");
  await expect(page.getByText("Reply sent")).toBeVisible();
  await expect(page.getByRole("list", { name: "Conversation" })).toContainText("a fix is on its way");
  await expect(page.locator("main")).toContainText("Waiting on user");
});

test("new tickets and replies arrive live and are marked unread", async ({ page }) => {
  await page.goto("/tickets");
  await settled(page);
  // The stand-in makes a ticket or a reply every 2 seconds in this run.
  await expect(page.getByRole("navigation", { name: "Admin sections" }).getByLabel(/unread/)).toBeVisible({ timeout: 20_000 });
});

test("the screen locks when idle, and drops what it showed", async ({ page }) => {
  await page.clock.install();
  await page.goto("/users/5");
  await settled(page);
  await page.clock.fastForward(16 * 60_000);
  await expect(page.getByText("Locked while you were away")).toBeVisible();
  await expect(page.getByTestId("email")).toHaveCount(0);
  await page.getByRole("button", { name: "Continue" }).click();
  await settled(page);
  await expect(page.getByTestId("email")).toBeVisible();
});

test("the served app carries the security headers", async ({ request }) => {
  const page = await request.get("/users/5");
  expect(page.status()).toBe(200);
  const h = page.headers();
  expect(h["content-security-policy"]).toContain("script-src 'self'");
  expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(h["x-frame-options"]).toBe("DENY");
  expect(h["referrer-policy"]).toBe("no-referrer");
  expect(h["cache-control"]).toBe("no-store");
  const api = await request.get("/bff/me");
  expect(api.headers()["cache-control"]).toBe("no-store");
  const refused = await request.get("/bff/me", { headers: { "X-Requested-With": "something-else" } });
  expect(refused.status()).toBe(403);
});
