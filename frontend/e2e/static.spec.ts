import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// The static edition (VITE_STATIC_DATA=1) served as plain files, exactly like GitHub Pages does.
// Requires a build at ../.static-site/GuFu (see `make static-test`).
const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = join(HERE, "..", ".static-site");
const PORT = 8090;
let proc: ChildProcess;

test.skip(!existsSync(join(SITE, "GuFu", "index.html")), "static site not built");

test.beforeAll(async () => {
  proc = spawn("python3", ["-m", "http.server", String(PORT), "--bind", "127.0.0.1"], { cwd: SITE, stdio: "ignore" });
  for (let i = 0; i < 60; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/GuFu/index.html`); if (r.ok) return; } catch { /* not up */ }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("static server did not start");
});
test.afterAll(() => { proc?.kill(); });

test("static edition works with no backend at all", async ({ page }) => {
  const base = `http://127.0.0.1:${PORT}/GuFu/`;
  await page.goto(base);
  await expect(page.getByTestId("stat-tiles")).toContainText(/[1-9]\d\d \/ \d+/, { timeout: 30_000 });
  await expect(page.getByText(/Data as of/)).toBeVisible();
  await page.getByLabel("Search companies").fill("msft");
  await page.getByRole("option").first().click();
  await expect(page).toHaveURL(/#\/company\/MSFT$/);
  await expect(page.getByTestId("price")).not.toHaveText("N/A");
  await page.getByTestId("tab-financials").click();
  await expect(page.getByTestId("coverage")).toContainText(/30 of 30 years/);
  await page.goto(`${base}#/screener?sector=Financials&pe_max=15&sort=pe&order=asc`);
  const total = page.getByTestId("screener-total");
  await expect(total).toContainText(/\d+ of \d+ companies/);
  const rows = page.getByTestId("screener-table").locator("tbody tr");
  expect(await rows.count()).toBeGreaterThan(0);
  await expect(rows.first()).toContainText("Financials");
});
