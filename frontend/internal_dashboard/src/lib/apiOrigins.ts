/**
 * Public API origins for the three FastAPI backends.
 * Override per environment via Vercel / Docker build args (NEXT_PUBLIC_*).
 */
function originFromEnv(value: string | undefined, fallback: string): string {
  return (value || fallback).replace(/\/$/, "");
}

export const PHASE1_API_ORIGIN = originFromEnv(
  process.env.NEXT_PUBLIC_PHASE1_API_URL,
  "http://localhost:8000",
);

export const PHASE2_API_ORIGIN = originFromEnv(
  process.env.NEXT_PUBLIC_PHASE2_API_URL,
  "http://localhost:8001",
);

export const PHASE3_API_ORIGIN = originFromEnv(
  process.env.NEXT_PUBLIC_PHASE3_API_URL,
  "http://localhost:8002",
);
