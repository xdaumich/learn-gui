function trimTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function envNumber(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

/** Derive a default origin from the current browser hostname + given port. */
function defaultOrigin(port: number): string {
  if (typeof window !== "undefined") {
    return `${window.location.protocol}//${window.location.hostname}:${port}`;
  }
  return `http://localhost:${port}`;
}

export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL ?? defaultOrigin(8000),
);

export const CAMERA_LIVE_GRACE_MS = envNumber(import.meta.env.VITE_CAMERA_LIVE_GRACE_MS, 4000);
export const TOPBAR_HOVER_DELAY_MS = envNumber(import.meta.env.VITE_TOPBAR_HOVER_DELAY_MS, 400);
