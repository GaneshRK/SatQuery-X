"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { authApi } from "../services/contractClient";

export interface UserProfile {
  id: number;
  full_name: string;
  email: string;
}

interface AuthContextType {
  user: UserProfile | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<any>;
  register: (payload: any) => Promise<any>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: async () => {},
  register: async () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const token = localStorage.getItem("satquery_access");
    if (!token) {
      setLoading(false);
      return;
    }

    authApi
      .me()
      .then(({ data }) => setUser(data))
      .catch(() => {
        localStorage.removeItem("satquery_access");
        localStorage.removeItem("satquery_refresh");
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const { data } = await authApi.login({ email, password });
    if (typeof window !== "undefined") {
      localStorage.setItem("satquery_access", data.access);
      if (data.refresh) localStorage.setItem("satquery_refresh", data.refresh);
    }
    setUser(data.user);
    return data;
  };

  const register = async (payload: any) => {
    const { data } = await authApi.register(payload);
    if (data.access && typeof window !== "undefined") {
      localStorage.setItem("satquery_access", data.access);
      if (data.refresh) localStorage.setItem("satquery_refresh", data.refresh);
      setUser(data.user);
    }
    return data;
  };

  const logout = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("satquery_access");
      localStorage.removeItem("satquery_refresh");
    }
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
