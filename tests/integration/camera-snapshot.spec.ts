import { test, expect } from "@playwright/test";

const VIDEO_SELECTOR = "[data-testid='camera-stream']";
const EXPECTED_LABELS = ["Left", "Center", "Right"];

test("renders three live camera tiles", async ({ page }) => {
  await page.goto("/");

  const tiles = page.locator(VIDEO_SELECTOR);
  await expect(tiles).toHaveCount(3, { timeout: 20_000 });

  const labels = await page
    .locator(".camera-tile .camera-label")
    .allTextContents();
  expect(labels).toEqual(EXPECTED_LABELS);
});

test("all three camera streams are live", async ({ page }) => {
  await page.goto("/");

  const tiles = page.locator(VIDEO_SELECTOR);
  await expect(tiles).toHaveCount(3, { timeout: 20_000 });

  await expect(async () => {
    const allLive = await tiles.evaluateAll((videos: HTMLVideoElement[]) =>
      videos.every((v) => {
        const tracks =
          v.srcObject && "getVideoTracks" in v.srcObject
            ? (v.srcObject as MediaStream).getVideoTracks()
            : [];
        return v.readyState >= 2 && tracks.some((t) => t.readyState === "live");
      }),
    );
    expect(allLive).toBe(true);
  }).toPass({ timeout: 20_000 });
});

test("snapshot: three cameras, no error banner", async ({ page }) => {
  await page.goto("/");

  const tiles = page.locator(VIDEO_SELECTOR);
  await expect(tiles).toHaveCount(3, { timeout: 20_000 });

  await expect(page.locator("[role='alert']")).toHaveCount(0);

  await page.screenshot({
    path: "docs/assets/screenshots/integration-3cam-snapshot.png",
    fullPage: true,
  });

  await expect(page).toHaveScreenshot("3cam-all-live.png");
});

test("video currentTime advances for all three streams", async ({ page }) => {
  await page.goto("/");

  const tiles = page.locator(VIDEO_SELECTOR);
  await expect(tiles).toHaveCount(3, { timeout: 20_000 });

  // Wait for streams to be live first
  await expect(async () => {
    const allLive = await tiles.evaluateAll((videos: HTMLVideoElement[]) =>
      videos.every((v) => v.readyState >= 2),
    );
    expect(allLive).toBe(true);
  }).toPass({ timeout: 20_000 });

  const t0 = await tiles.evaluateAll((videos: HTMLVideoElement[]) =>
    videos.map((v) => v.currentTime),
  );

  await page.waitForTimeout(2_000);

  const t1 = await tiles.evaluateAll((videos: HTMLVideoElement[]) =>
    videos.map((v) => v.currentTime),
  );

  for (let i = 0; i < 3; i++) {
    expect(t1[i]).toBeGreaterThan(t0[i]);
  }
});
