"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { Spinner } from "@/components/ui/Spinner";

export default function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  useEffect(() => { if (!isLoading) router.replace(isAuthenticated ? "/dashboard" : "/auth/login"); }, [isLoading, isAuthenticated, router]);
  return <div className="flex items-center justify-center min-h-screen bg-surface"><Spinner size="lg" /></div>;
}
