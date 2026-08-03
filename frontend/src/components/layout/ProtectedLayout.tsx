"use client";
import React from "react";
import { cn } from "@/lib/utils";
import { useRequireAuth } from "@/hooks/useAuth";
import { Spinner } from "@/components/ui/Spinner";
import { Sidebar } from "./Sidebar";

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useRequireAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-canvas transition-colors duration-200">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-canvas transition-colors duration-200">
      <Sidebar />
      <main className="ml-[250px] min-h-screen">
        <div className="max-w-[1200px] mx-auto px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  );
}
