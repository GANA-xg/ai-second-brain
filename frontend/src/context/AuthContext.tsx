"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import type { UserResponse } from "@/lib/types";
import { authApi } from "@/lib/api-client";
import {
  setAccessToken,
  setRefreshToken,
  clearTokens,
  getRefreshToken,
} from "@/lib/api";

interface AuthState {
  user: UserResponse | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, fullName: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount, try to restore session from stored tokens
  useEffect(() => {
    const storedAccess = sessionStorage.getItem("access_token");
    const storedRefresh = localStorage.getItem("refresh_token");
    if (storedAccess && storedRefresh) {
      setAccessToken(storedAccess);
      setRefreshToken(storedRefresh);
      // We could verify the token by calling a /me endpoint, but the
      // backend doesn't expose one — we trust the stored tokens. If
      // they're expired, the 401 interceptor will handle it.
      // For now, set a minimal user placeholder; the auth guard
      // middleware runs first anyway.
      setUser({
        id: "",
        email: "",
        full_name: "",
        is_active: true,
      });
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    setAccessToken(res.access_token);
    setRefreshToken(res.refresh_token);
    sessionStorage.setItem("access_token", res.access_token);
    localStorage.setItem("refresh_token", res.refresh_token);
    // We don't have a /me endpoint; the user will be fetched
    // implicitly when they hit the dashboard and the token works.
    setUser({
      id: "",
      email,
      full_name: "",
      is_active: true,
    });
  }, []);

  const signup = useCallback(
    async (email: string, fullName: string, password: string) => {
      await authApi.register({ email, full_name: fullName, password });
      // Auto-login after signup
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(async () => {
    try {
      const rt = getRefreshToken();
      if (rt) {
        await authApi.logout(rt);
      }
    } catch {
      // Logout server-side may fail if token already expired; clear locally anyway
    }
    clearTokens();
    sessionStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        signup,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
