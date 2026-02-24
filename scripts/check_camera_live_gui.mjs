#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, firefox, webkit } from "playwright";

const thisFile = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(thisFile), "..");

const apiBaseUrl = (process.env.CAMERA_GUARD_API_BASE_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const guiUrl = process.env.CAMERA_GUARD_GUI_URL || "http://localhost:5173";
const browserName = (process.env.CAMERA_GUARD_GUI_BROWSER || "chromium").toLowerCase();
const chromiumArgsRaw =
  process.env.CAMERA_GUARD_CHROMIUM_ARGS ||
  "--enable-features=WebRtcAllowH265Receive,PlatformHEVCDecoderSupport --force-fieldtrials=WebRTC-Video-H26xPacketBuffer/Enable/";
const timeoutMs = Number(process.env.CAMERA_GUARD_TIMEOUT_MS || 20_000);
const pollMs = Number(process.env.CAMERA_GUARD_POLL_MS || 500);
const minCameras = Number(process.env.CAMERA_GUARD_MIN_CAMERAS || 3);
const successSnapshotPath =
  process.env.CAMERA_GUARD_GUI_SUCCESS_SNAPSHOT ||
  path.join(repoRoot, "docs/assets/screenshots/camera-live-guard-success.png");
const failureSnapshotPath =
  process.env.CAMERA_GUARD_GUI_FAILURE_SNAPSHOT ||
  path.join(repoRoot, "docs/assets/screenshots/camera-live-guard-failure.png");

const videoSelector = "[data-testid='camera-stream']";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  } finally {
    clearTimeout(timeout);
  }
}

async function waitForExpectedCameras(deadline) {
  const healthUrl = `${apiBaseUrl}/health`;
  const camerasUrl = `${apiBaseUrl}/webrtc/cameras`;
  let lastError = null;

  let best = [];

  while (Date.now() < deadline) {
    try {
      const health = await fetchJson(healthUrl);
      if (health?.status !== "ok") {
        throw new Error(`Unexpected health payload: ${JSON.stringify(health)}`);
      }

      const cameras = await fetchJson(camerasUrl);
      if (!Array.isArray(cameras)) {
        throw new Error("/webrtc/cameras response is not an array.");
      }
      const names = cameras.filter((name) => typeof name === "string");
      if (names.length > best.length) {
        best = names;
        console.log(
          `[camera-guard:gui] Discovered ${best.length} camera(s) so far: ${best.join(", ")}.`,
        );
      }
      if (best.length > 0 && (minCameras <= 0 || best.length >= minCameras)) {
        return best;
      }
      if (names.length === 0) {
        throw new Error("No cameras detected by /webrtc/cameras.");
      }
      await sleep(pollMs);
    } catch (error) {
      lastError = error;
      await sleep(pollMs);
    }
  }

  if (best.length > 0) {
    return best;
  }

  throw new Error(`Timed out waiting for camera API readiness (${String(lastError)})`);
}

async function readVideoStats(page) {
  const locator = page.locator(videoSelector);
  const tileCount = await locator.count();
  const stats = await locator.evaluateAll((videos) =>
    videos.map((video) => {
      const stream = video.srcObject;
      const tracks =
        stream && typeof stream.getVideoTracks === "function" ? stream.getVideoTracks() : [];
      const liveTracks = tracks.filter((track) => track.readyState === "live").length;
      return {
        readyState: video.readyState,
        paused: video.paused,
        liveTracks,
      };
    }),
  );

  const liveCount = stats.filter((item) => item.readyState >= 2 && item.liveTracks > 0).length;
  return { tileCount, liveCount, stats };
}

async function ensureSnapshotDir(snapshotPath) {
  await fs.mkdir(path.dirname(snapshotPath), { recursive: true });
}

async function readCurrentTimes(page) {
  const locator = page.locator(videoSelector);
  return locator.evaluateAll((videos) => videos.map((v) => v.currentTime));
}

async function verifyCurrentTimeAdvancing(page, { pollIntervalMs = 2000 } = {}) {
  const t0 = await readCurrentTimes(page);
  await sleep(pollIntervalMs);
  const t1 = await readCurrentTimes(page);
  const results = t0.map((val, i) => ({
    index: i,
    t0: val,
    t1: t1[i],
    advancing: t1[i] > val,
  }));
  const advancingCount = results.filter((r) => r.advancing).length;
  return { results, advancingCount };
}

async function run() {
  const deadline = Date.now() + timeoutMs;
  const expectedCameras = await waitForExpectedCameras(deadline);
  const expectedCount = expectedCameras.length;
  console.log(
    `[camera-guard:gui] Expected cameras: ${expectedCount} (${expectedCameras.join(", ")}).`,
  );
  if (minCameras > 0 && expectedCount < minCameras) {
    console.error(
      `[camera-guard:gui] ERROR: only ${expectedCount} camera(s) detected, minimum required is ${minCameras}.`,
    );
    return 1;
  }

  let browser;
  let page;
  let lastStats = { tileCount: 0, liveCount: 0, stats: [] };
  let lastNavigationError = null;
  let didNavigate = false;

  try {
    const browserTypes = {
      chromium,
      firefox,
      webkit,
    };
    const browserType = browserTypes[browserName];
    if (!browserType) {
      throw new Error(
        `Unsupported CAMERA_GUARD_GUI_BROWSER='${browserName}'. Use chromium, firefox, or webkit.`,
      );
    }

    const launchOptions = { headless: true };
    if (browserName === "chromium") {
      const chromiumArgs = chromiumArgsRaw
        .split(/\s+/)
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      if (chromiumArgs.length > 0) {
        launchOptions.args = chromiumArgs;
      }
    }
    browser = await browserType.launch(launchOptions);
    page = await browser.newPage();

    while (Date.now() < deadline) {
      if (!didNavigate) {
        try {
          await page.goto(guiUrl, {
            waitUntil: "domcontentloaded",
            timeout: Math.min(pollMs * 4, 3_000),
          });
          didNavigate = true;
        } catch (error) {
          lastNavigationError = error;
          await sleep(pollMs);
          continue;
        }
      }

      lastStats = await readVideoStats(page);
      if (lastStats.tileCount >= expectedCount && lastStats.liveCount >= expectedCount) {
        const { results, advancingCount } = await verifyCurrentTimeAdvancing(page);
        if (advancingCount < expectedCount) {
          const detail = results
            .map((r) => `cam${r.index}: t0=${r.t0.toFixed(3)} t1=${r.t1.toFixed(3)} advancing=${r.advancing}`)
            .join(", ");
          await ensureSnapshotDir(failureSnapshotPath);
          await page.screenshot({ path: failureSnapshotPath, fullPage: true });
          console.error(
            `[camera-guard:gui] ERROR: decode check failed — ${advancingCount}/${expectedCount} advancing (${detail}). Snapshot: ${failureSnapshotPath}`,
          );
          return 1;
        }
        await ensureSnapshotDir(successSnapshotPath);
        await page.screenshot({ path: successSnapshotPath, fullPage: true });
        console.log(
          `[camera-guard:gui] PASS: ${lastStats.liveCount}/${expectedCount} live camera tiles, decode verified (${advancingCount}/${expectedCount} advancing). Snapshot: ${successSnapshotPath}`,
        );
        return 0;
      }
      await sleep(pollMs);
    }

    await ensureSnapshotDir(failureSnapshotPath);
    await page.screenshot({ path: failureSnapshotPath, fullPage: true });
    const navHint = lastNavigationError ? ` last_navigation_error=${String(lastNavigationError)}` : "";
    console.error(
      "[camera-guard:gui] ERROR: "
        + `only ${lastStats.liveCount}/${expectedCount} live camera tiles `
        + `(tiles_seen=${lastStats.tileCount}). `
        + `Snapshot: ${failureSnapshotPath}.${navHint}`,
    );
    return 1;
  } finally {
    if (page) {
      await page.close();
    }
    if (browser) {
      await browser.close();
    }
  }
}

run()
  .then((code) => {
    process.exit(code);
  })
  .catch((error) => {
    console.error(`[camera-guard:gui] ERROR: ${error}`);
    process.exit(1);
  });
