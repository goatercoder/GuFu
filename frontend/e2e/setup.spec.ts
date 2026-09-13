import { expect, test } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");

// Live mode with no SEC User-Agent: the backend must boot, serve the built frontend itself on one port,
// show the one-time setup card, and accept name + email. No network is needed for this.
const PORT = 8012;
let proc: ChildProcess;
let dir: string;

test.beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "gufu-setup-"));
  proc = spawn(join(ROOT, ".venv", "bin", "python"), ["-m", "uvicorn", "gufu.main:app", "--port", String(PORT)], {
    cwd: join(ROOT, "backend"),
    env: { ...process.env, GUFU_FIXTURE_MODE: "0", GUFU_SEC_USER_AGENT: "", GUFU_DB_PATH: join(dir, "t.sqlite"), GUFU_ENV_PATH: join(dir, ".env"), GUFU_AUTO_BUILD_ON_START: "0" },
    stdio: "ignore",
  });
  for (let i = 0; i < 120; i++) {
    try { const r = await fetch(`http://127.0.0.1:${PORT}/api/health`); if (r.ok) return; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("live-mode backend did not start");
});

test.afterAll(() => { proc?.kill(); });

test("first run shows the setup card and accepts name + email", async ({ page }) => {
  await page.goto(`http://127.0.0.1:${PORT}/`);
  const card = page.getByTestId("setup-card");
  await expect(card).toBeVisible();
  await expect(card).toContainText("GuFu/0.1 (Your Name; you@example.com)");
  await page.getByLabel("Your name").fill("Jane Doe");
  await page.getByLabel("Your email").fill("jane@example.com");
  await expect(card).toContainText("GuFu/0.1 (Jane Doe; jane@example.com)");
  await page.screenshot({ path: "test-results/setup.png" });
  await page.getByRole("button", { name: "Start GuFu" }).click();
  await expect(card).toBeHidden({ timeout: 15_000 });
  await expect(page.getByRole("heading", { name: /S&P 500 stock research/i })).toBeVisible();
  expect(readFileSync(join(dir, ".env"), "utf-8")).toContain('GUFU_SEC_USER_AGENT="GuFu/0.1 (Jane Doe; jane@example.com)"');
  // deep links are served by the backend as an SPA (this is what the launcher relies on)
  await page.goto(`http://127.0.0.1:${PORT}/screener`);
  await expect(page.getByRole("heading", { name: "Screener" })).toBeVisible();
});
