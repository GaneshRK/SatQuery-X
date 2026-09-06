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

  // Handle Token Expiry & Auto-Reauthentication
  if (response.status === 401 && typeof window !== "undefined") {
    let newAccessToken: string | null = null;
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
          newAccessToken = data.access;
          localStorage.setItem("satquery_access_token", data.access);
        }
      } catch (err) {
        console.warn("Token refresh failed:", err);
      }
    }

    // If refresh failed or was absent, re-authenticate with default analyst account
    if (!newAccessToken) {
      try {
        const loginRes = await fetch(`${BASE_URL}/auth/login/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: "analyst", password: "satquery2026" }),
        });
        if (loginRes.ok) {
          const loginData = await loginRes.json();
          newAccessToken = loginData.access;
          localStorage.setItem("satquery_access_token", loginData.access);
          if (loginData.refresh) {
            localStorage.setItem("satquery_refresh_token", loginData.refresh);
          }
        }
      } catch (loginErr) {
        console.error("Auto-login fallback failed:", loginErr);
      }
    }

    if (newAccessToken) {
      headers.set("Authorization", `Bearer ${newAccessToken}`);
      const retryRes = await fetch(url, { ...options, headers });
      if (retryRes.status === 204) return {} as T;
      if (!retryRes.ok) throw new Error(await retryRes.text());
      return retryRes.json();
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
