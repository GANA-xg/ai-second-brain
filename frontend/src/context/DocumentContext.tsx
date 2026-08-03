"use client";

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
} from "react";
import type { DocumentResponse } from "@/lib/types";
import { documentsApi } from "@/lib/api-client";

interface DocumentState {
  documents: DocumentResponse[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const DocumentContext = createContext<DocumentState | undefined>(undefined);

export function DocumentProvider({ children }: { children: React.ReactNode }) {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const refresh = useCallback(async () => {
    // Don't fetch documents if there's no access token — avoids 401 → refresh → redirect loop
    const hasToken =
      typeof window !== "undefined" &&
      (localStorage.getItem("access_token") || sessionStorage.getItem("access_token"));
    if (!hasToken) {
      if (mountedRef.current) setIsLoading(false);
      return;
    }
    try {
      setError(null);
      const data = await documentsApi.list();
      if (mountedRef.current) {
        setDocuments(data.documents);
      }
    } catch (err) {
      if (mountedRef.current) {
        const msg = err instanceof Error ? err.message : "Failed to load documents";
        setError(msg);
        console.error("[DocumentContext] fetch error:", msg);
      }
    } finally {
      if (mountedRef.current) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    setIsLoading(true);
    refresh();
    return () => { mountedRef.current = false; };
  }, [refresh]);

  return (
    <DocumentContext.Provider value={{ documents, isLoading, error, refresh }}>
      {children}
    </DocumentContext.Provider>
  );
}

export function useDocuments(): DocumentState {
  const ctx = useContext(DocumentContext);
  if (!ctx) throw new Error("useDocuments must be used within DocumentProvider");
  return ctx;
}
