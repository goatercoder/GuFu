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

test("30-Y Financials tab: five GuruFocus-style sections, 30 years + TTM + quarters, sparklines, CSV", async ({ page }) => {
  await page.goto("/company/AAPL");
  await expect(page.getByTestId("price")).not.toHaveText("N/A", { timeout: 60_000 });
  await expect(page.getByTestId("rank-badges")).toContainText("Financial Strength");
  await page.getByTestId("tab-financials").click();
  await expect(page).toHaveURL(/\/company\/AAPL\/financials$/);
  await expect(page.getByTestId("coverage")).toContainText(/30 of 30 years available/, { timeout: 90_000 });
  for (const id of ["per-share", "ratios", "income", "balance", "cashflow"]) await expect(page.getByTestId(`section-${id}`)).toBeVisible();
  const income = page.getByTestId("section-income");
  const headers = income.locator("thead th");
  const texts = await headers.allTextContents();
  const annual = texts.filter((t) => /^[A-Z][a-z]{2} \d{2}$/.test(t.trim()));
  expect(annual.length).toBe(35); // 30 fiscal years + 5 quarters (same label style)
  expect(texts).toContain("TTM");
  expect(await income.locator("th.legacy").count()).toBeGreaterThan(10);
  expect(await income.locator("svg").count()).toBeGreaterThan(5); // trend sparklines
  // no horizontal overflow on a wide screen: the table fits its container
  const box = await income.locator("table").boundingBox();
  const wrap = await income.locator(".fy-scroll").boundingBox();
  expect(box!.width).toBeLessThanOrEqual(wrap!.width + 1);
  await expect(page.getByTestId("section-ratios")).toContainText("P/E Ratio");
  await expect(page.getByTestId("section-per-share")).toContainText("Month End Stock Price");
  await page.getByRole("button", { name: "YoY %" }).click();
  await expect(income.locator("tbody td.num").filter({ hasText: /%$/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "$", exact: true }).click();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("csv-button").click()]);
  expect(download.suggestedFilename()).toBe("AAPL_30y_financials.csv");
  await page.screenshot({ path: "test-results/financials.png", fullPage: true });
});

test("valuation, dividend and peers tabs render", async ({ page }) => {
  // peers are drawn from the universe index, which fills in as the background build runs
  await page.goto("/");
  await expect.poll(async () => {
    const r = await page.request.get("/api/health");
    return ((await r.json()) as { metrics_cached: number }).metrics_cached;
  }, { timeout: 120_000, intervals: [2000] }).toBeGreaterThan(400);
  await page.goto("/company/MSFT/valuation");
  await expect(page.getByTestId("valuation-page")).toContainText("Historical valuation", { timeout: 60_000 });
  await expect(page.getByTestId("valuation-page").locator("svg.recharts-surface").first()).toBeVisible();
  await page.getByTestId("tab-dividend").click();
  await expect(page.getByTestId("dividend-page")).toContainText("Dividend history");
  await page.getByTestId("tab-peers").click();
  const rows = page.getByTestId("peers-page").locator("tbody tr");
  await expect(rows.first()).toContainText("MSFT");
  await expect.poll(() => rows.count()).toBeGreaterThan(3);
  await page.screenshot({ path: "test-results/peers.png", fullPage: true });
});
