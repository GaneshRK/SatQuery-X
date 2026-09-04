/**
 * Base API client with JWT header injection and auto-refresh per §14.4
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = endpoint.startsWith("http") ? endpoint : `${BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  const token = typeof window !== "undefined" ? localStorage.getItem("satquery_access_token") : null;
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Handle Token Expiry
  if (response.status === 401 && typeof window !== "undefined") {
    const refreshToken = localStorage.getItem("satquery_refresh_token");
    if (refreshToken) {
      try {
        const refreshRes = await fetch(`${BASE_URL}/auth/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh: refreshToken }),
        });
        if (refreshRes.ok) {
          const data = await refreshRes.json();
          localStorage.setItem("satquery_access_token", data.access);
          headers.set("Authorization", `Bearer ${data.access}`);
          const retryRes = await fetch(url, { ...options, headers });
          if (!retryRes.ok) throw new Error(await retryRes.text());
          return retryRes.json();
        }
      } catch (err) {
        console.error("Token refresh failed", err);
      }
    }
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `HTTP Error ${response.status}`);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}
