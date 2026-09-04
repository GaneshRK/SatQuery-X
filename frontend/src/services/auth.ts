import { apiRequest } from "./api";

export interface UserProfile {
  id: number;
  username: string;
  email: string;
  role: "demo" | "judge" | "admin";
}

export async function login(username: string, password: string):Promise<{ access: string; refresh: string }> {
  const data = await apiRequest<{ access: string; refresh: string }>("/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("satquery_access_token", data.access);
    localStorage.setItem("satquery_refresh_token", data.refresh);
  }
  return data;
}

export async function getCurrentUser(): Promise<UserProfile> {
  return apiRequest<UserProfile>("/auth/me/");
}

export function logout(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("satquery_access_token");
    localStorage.removeItem("satquery_refresh_token");
  }
}
