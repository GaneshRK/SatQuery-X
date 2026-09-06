/**
 * Typed client connecting Next.js App Router to the Django REST contract at /api/
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

async function request<T = any>(endpoint: string, options: RequestInit = {}): Promise<{ data: T }> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;
  const headers = new Headers(options.headers || {});

  const token = typeof window !== "undefined" ? localStorage.getItem("satquery_access") : null;
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res = await fetch(url, { ...options, headers });

  // Handle Token Refresh
  if (res.status === 401 && typeof window !== "undefined") {
    const refresh = localStorage.getItem("satquery_refresh");
    if (refresh) {
      try {
        const refreshRes = await fetch(`${API_BASE}/auth/token/refresh/`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh }),
        });
        if (refreshRes.ok) {
          const rData = await refreshRes.json();
          localStorage.setItem("satquery_access", rData.access);
          headers.set("Authorization", `Bearer ${rData.access}`);
          res = await fetch(url, { ...options, headers });
        }
      } catch (err) {
        console.warn("Token refresh error:", err);
      }
    }
  }

  if (!res.ok) {
    let errData: any;
    try {
      errData = await res.json();
    } catch {
      errData = { detail: await res.text() || `HTTP ${res.status}` };
    }
    const error: any = new Error(errData.detail || errData.error || `HTTP ${res.status}`);
    error.response = { data: errData, status: res.status };
    throw error;
  }

  if (res.status === 204) {
    return { data: {} as T };
  }

  const data = await res.json();
  return { data };
}

export const authApi = {
  register: (payload: any) =>
    request("/auth/register/", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload: any) =>
    request("/auth/login/", { method: "POST", body: JSON.stringify(payload) }),
  me: () =>
    request("/auth/me/"),
  refresh: (payload: any) =>
    request("/auth/token/refresh/", { method: "POST", body: JSON.stringify(payload) }),
  forgotPassword: (payload: any) =>
    request("/auth/forgot-password/", { method: "POST", body: JSON.stringify(payload) }),
  verifyEmail: (payload: any) =>
    request("/auth/verify-email/", { method: "POST", body: JSON.stringify(payload) }),
};

export const analysisApi = {
  query: (payload: any) => {
    if (payload instanceof FormData) {
      return request("/analysis/query/", { method: "POST", body: payload });
    }
    return request("/analysis/query/", { method: "POST", body: JSON.stringify(payload) });
  },
  history: () =>
    request("/analysis/history/"),
  detail: (id: string) =>
    request(`/analysis/${id}/`),
  createProject: (payload: any) =>
    request("/projects/", { method: "POST", body: JSON.stringify(payload) }),
  projects: () =>
    request("/projects/"),
};
