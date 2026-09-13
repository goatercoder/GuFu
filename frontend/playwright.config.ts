import { defineConfig } from "@playwright/test";

// Runs the backend in fixture mode (no network) + the built frontend, then smoke-tests the three pages.
const API = 8011;
const WEB = 4173;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  retries: 0,
  use: { baseURL: `http://127.0.0.1:${WEB}`, viewport: { width: 1400, height: 1000 } },
  webServer: [
    {
      command: `cd ../backend && GUFU_FIXTURE_MODE=1 GUFU_DB_PATH=../frontend/test-results/e2e.sqlite ../.venv/bin/python -m uvicorn gufu.main:app --port ${API}`,
      url: `http://127.0.0.1:${API}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `GUFU_API_URL=http://127.0.0.1:${API} npm run preview`,
      url: `http://127.0.0.1:${WEB}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
