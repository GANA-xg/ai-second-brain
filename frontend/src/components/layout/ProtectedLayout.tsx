"use client";
import { Sidebar } from "./Sidebar";
import { useRequireAuth } from "@/hooks/useAuth";
import { Spinner } from "@/components/ui/Spinner";

export function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const { isLoading } = useRequireAuth();
  if (isLoading) return <div className="flex items-center justify-center min-h-screen bg-surface"><Spinner size="lg" /></div>;
  return (
    <div className="flex min-h-screen bg-surface">
      <Sidebar />
      <main className="flex-1 ml-56 min-h-screen">
        <div className="max-w-[var(--container-max)] mx-auto px-8 py-10">{children}</div>
      </main>
    </div>
  );
}
