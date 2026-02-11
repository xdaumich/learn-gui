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

export const API_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000",
);
export const WHEP_BASE_URL = trimTrailingSlash(
  import.meta.env.VITE_WHEP_BASE_URL ?? "http://localhost:8889",
);

export const CAMERA_LIVE_GRACE_MS = envNumber(import.meta.env.VITE_CAMERA_LIVE_GRACE_MS, 4000);
export const WHEP_CONNECT_RETRY_MS = envNumber(
  import.meta.env.VITE_WHEP_CONNECT_RETRY_MS,
  400,
);
export const WHEP_CONNECT_TIMEOUT_MS = envNumber(
  import.meta.env.VITE_WHEP_CONNECT_TIMEOUT_MS,
  12000,
);
export const ICE_GATHER_TIMEOUT_MS = envNumber(import.meta.env.VITE_ICE_GATHER_TIMEOUT_MS, 2000);
export const TOPBAR_HOVER_DELAY_MS = envNumber(import.meta.env.VITE_TOPBAR_HOVER_DELAY_MS, 400);

export const RERUN_WEB_PORT = envNumber(import.meta.env.VITE_RERUN_WEB_PORT, 9090);
export const RERUN_GRPC_PORT = envNumber(import.meta.env.VITE_RERUN_GRPC_PORT, 9876);
export const RERUN_WEB_ORIGIN = trimTrailingSlash(
  import.meta.env.VITE_RERUN_WEB_ORIGIN ?? `http://localhost:${RERUN_WEB_PORT}`,
);
export const RERUN_GRPC_ORIGIN = trimTrailingSlash(
  import.meta.env.VITE_RERUN_GRPC_ORIGIN ?? `http://localhost:${RERUN_GRPC_PORT}`,
);

export const RERUN_WEB_URL = `${RERUN_WEB_ORIGIN}?url=${encodeURIComponent(
  `rerun+${RERUN_GRPC_ORIGIN}/proxy`,
)}`;
