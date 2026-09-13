import { expect, test } from "@playwright/test";

// The backend runs with GUFU_FIXTURE_MODE=1 (bundled sample data), so these tests need no network.

test("home page renders tiles, sector chart and search navigates", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /S&P 500 stock research/i })).toBeVisible();
  await expect(page.getByTestId("stat-tiles")).toBeVisible();
  // wait until the fixture build has populated the cache
  await expect.poll(async () => (await page.getByTestId("stat-tiles").textContent()) ?? "", { timeout: 60_000 }).not.toContain("0 / ");
  await expect(page.locator("svg.recharts-surface").first()).toBeVisible();
  await page.getByLabel("Search companies").fill("appl");
  await page.getByRole("option").first().click();
  await expect(page).toHaveURL(/\/company\/AAPL$/);
  // screenshot the overview once the background build has populated the cache
  await expect.poll(async () => {
    const r = await page.request.get("/api/health");
    return ((await r.json()) as { metrics_cached: number }).metrics_cached;
  }, { timeout: 120_000, intervals: [2000] }).toBeGreaterThan(400);
  await page.goto("/");
  await expect(page.getByTestId("stat-tiles")).toContainText(/[1-9]\d\d \/ \d+/);
  await expect(page.locator("svg.recharts-surface").first()).toBeVisible();
  await page.screenshot({ path: "test-results/home.png", fullPage: true });
});

test("company page shows price, metrics, two charts and quarterly toggle", async ({ page }) => {
  await page.goto("/company/MSFT");
  await expect(page.getByTestId("price")).not.toHaveText("N/A", { timeout: 60_000 });
  await expect(page.getByTestId("metric-table")).toHaveCount(6);
  await expect(page.getByTestId("price-chart").locator("svg.recharts-surface")).toBeVisible();
  const fin = page.getByTestId("financial-chart");
  await expect(fin.locator("svg.recharts-surface")).toBeVisible();
  const annualBars = await fin.locator(".recharts-bar-rectangle").count();
  expect(annualBars).toBeGreaterThan(5);
  await fin.getByRole("button", { name: "Quarterly" }).click();
  await expect.poll(async () => fin.locator(".recharts-bar-rectangle").count()).toBeGreaterThan(annualBars);
  await expect(page.getByTestId("dcf")).toContainText("Fair value / share");
  await page.getByRole("button", { name: /Piotroski F-Score/i }).click();
  await expect(page.getByText("Positive net income")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText("Positive net income")).toBeHidden();
  await page.screenshot({ path: "test-results/company.png", fullPage: true });
});

test("screener filters reduce the match count and sorting works", async ({ page }) => {
  await page.goto("/screener");
  const total = page.getByTestId("screener-total");
  // the fixture-mode build takes ~30s on first start; wait until most of the universe has metrics
  await expect.poll(async () => {
    const r = await page.request.get("/api/health");
    return ((await r.json()) as { metrics_cached: number }).metrics_cached;
  }, { timeout: 120_000, intervals: [2000] }).toBeGreaterThan(400);
  await page.reload();
  await expect(total).toContainText(/\d+ of \d+ companies/, { timeout: 60_000 });
  const before = parseInt(((await total.textContent()) ?? "0").split(" ")[0], 10);
  expect(before).toBeGreaterThan(400);
  await page.getByLabel("P/E maximum").fill("12");
  await expect.poll(async () => parseInt(((await total.textContent()) ?? "0").split(" ")[0], 10)).toBeLessThan(before);
  const peHeader = page.getByTestId("screener-table").locator("th", { hasText: /^P\/E \(TTM\)/ });
  await peHeader.click();
  await expect(peHeader).toContainText("▼");
  const rows = page.getByTestId("screener-table").locator("tbody tr");
  expect(await rows.count()).toBeGreaterThan(0);
  await page.screenshot({ path: "test-results/screener.png", fullPage: true });
});

test("30-Y Financials tab shows three decades with legacy sources and CSV export", async ({ page }) => {
  await page.goto("/company/AAPL");
  await expect(page.getByTestId("price")).not.toHaveText("N/A", { timeout: 60_000 });
  await page.getByTestId("tab-financials").click();
  await expect(page).toHaveURL(/\/company\/AAPL\/financials$/);
  const table = page.getByTestId("financials-table");
  await expect(table).toBeVisible({ timeout: 60_000 });
  // wait for the older-filing extraction to finish (fixture mode: seconds)
  await expect(page.getByTestId("coverage")).toContainText(/30 of 30 years available/, { timeout: 90_000 });
  const yearHeaders = table.locator("thead th").filter({ hasText: /^FY\d{4}/ });
  expect(await yearHeaders.count()).toBe(30);
  expect(await table.locator(".legacy-tag").count()).toBeGreaterThan(10);
  await expect(table).toContainText("Income Statement");
  await expect(table).toContainText("Balance Sheet");
  await expect(table).toContainText("Cash Flow");
  await expect(table).toContainText("Per Share");
  await expect(table).toContainText("Ratios");
  // a legacy revenue cell has a value and a source tooltip pointing at the filing
  const revenueRow = table.locator("tbody tr", { hasText: /^Revenue/ }).first();
  const firstLegacyCell = revenueRow.locator("td.legacy-cell").first();
  await expect(firstLegacyCell).not.toHaveText("–");
  expect(await firstLegacyCell.getAttribute("title")).toMatch(/From the 10-K/);
  // CSV export is wired to a download
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("csv-button").click()]);
  expect(download.suggestedFilename()).toBe("AAPL_annual_financials.csv");
  await page.screenshot({ path: "test-results/financials.png", fullPage: true });
  // quarterly view is XBRL-only and still renders
  await page.getByRole("button", { name: "Quarterly" }).last().click();
  await expect(table.locator("thead th").filter({ hasText: /^Q\d '/ }).first()).toBeVisible();
});
