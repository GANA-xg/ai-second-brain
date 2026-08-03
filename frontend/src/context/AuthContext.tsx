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
    const storedAccess = localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
    const storedRefresh = localStorage.getItem("refresh_token");
    if (storedAccess && storedRefresh) {
      setAccessToken(storedAccess);
      setRefreshToken(storedRefresh);
      // Persist to both stores for cross-tab resilience
      localStorage.setItem("access_token", storedAccess);
      sessionStorage.setItem("access_token", storedAccess);
      setUser({
        id: "",
        email: "",
        full_name: "",
        is_active: true,
        username: null,
        bio: null,
        avatar_url: null,
      });
    }
    setIsLoading(false);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    setAccessToken(res.access_token);
    setRefreshToken(res.refresh_token);
    localStorage.setItem("access_token", res.access_token);
    sessionStorage.setItem("access_token", res.access_token);
    localStorage.setItem("refresh_token", res.refresh_token);
    // We don't have a /me endpoint; the user will be fetched
    // implicitly when they hit the dashboard and the token works.
    setUser({
      id: "",
      email,
      full_name: "",
      is_active: true,
      username: null,
      bio: null,
      avatar_url: null,
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
    localStorage.removeItem("access_token");
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
