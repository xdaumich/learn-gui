import { defineConfig, devices } from "@playwright/test";
import { dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: __dirname,
  workers: 1,
  timeout: 60_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          args: [
            "--enable-features=WebRtcAllowH265Receive,PlatformHEVCDecoderSupport",
          ],
        },
      },
    },
  ],
  outputDir: dirname(dirname(__dirname)) + "/docs/assets/screenshots",
});
