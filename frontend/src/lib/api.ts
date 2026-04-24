/** KeaBuilder API client for the frontend. */

// In production (Vercel), use relative paths so requests go through Next.js rewrites
// (same-origin, no CORS needed). Only use the full backend URL for local development
// when rewrites aren't available.
const IS_BROWSER = typeof window !== "undefined";
const BACKEND_URL = IS_BROWSER
  ? ""  // Browser: always use relative paths → Vercel rewrites proxy to backend
  : (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
export const API_BASE = BACKEND_URL + "/api/v1";
const REQUEST_TIMEOUT_MS = 30_000;

/** Resolve a relative storage path (e.g. /storage/...) to the full backend URL. */
export function storageUrl(path: string): string {
  if (!path) return path;
  // Already absolute
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return BACKEND_URL + path;
}
const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1_000;

export interface LeadInput {
  name: string;
  email: string;
  company?: string;
  company_size?: string;
  budget_range?: string;
  timeline?: string;
  use_case?: string;
  phone?: string;
  industry?: string;
}

export interface GenerateRequest {
  type: "image" | "video" | "voice";
  prompt: string;
  style?: string;
  dimensions?: { width: number; height: number };
  voice_id?: string;
  user_id: string;
  workspace_id: string;
}

export interface SimilaritySearchRequest {
  query: string;
  workspace_id: string;
  embed_type: "text" | "clip" | "face";
  top_k: number;
}

async function apiCall<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Include API key if configured
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const res = await fetch(`${API_BASE}${path}`, {
        headers,
        signal: controller.signal,
        ...options,
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));
        // Don't retry client errors (4xx)
        if (res.status >= 400 && res.status < 500) {
          throw new Error(error.detail || `API error: ${res.status}`);
        }
        throw new Error(error.detail || `API error: ${res.status}`);
      }

      return res.json();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));

      // Don't retry aborts or client errors
      if (lastError.name === "AbortError") {
        throw new Error("Request timed out");
      }

      if (attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, RETRY_DELAY_MS * (attempt + 1)));
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }

  throw lastError || new Error("Request failed");
}

// Q1: Lead Classification
export async function classifyLead(lead: LeadInput) {
  return apiCall("/leads/classify", {
    method: "POST",
    body: JSON.stringify(lead),
  });
}

export async function listLeads(classification?: string) {
  const params = classification ? `?classification=${classification}` : "";
  return apiCall(`/leads/${params}`);
}

// Q2: Content Generation
export async function generateContent(req: GenerateRequest) {
  return apiCall("/generate", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// Q4: Similarity Search
export async function searchSimilar(req: SimilaritySearchRequest) {
  return apiCall("/search/similar", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

// Assets
export async function listAssets(workspaceId: string, type?: string, page = 1) {
  const params = new URLSearchParams({ workspace_id: workspaceId, page: String(page) });
  if (type) params.set("type", type);
  return apiCall(`/assets/?${params}`);
}

// Health
export async function healthCheck() {
  return apiCall("/health");
}
