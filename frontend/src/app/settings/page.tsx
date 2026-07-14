"use client";
import React, { useState, useEffect, useCallback } from "react";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { MemoryCard } from "@/components/memories/MemoryCard";
import { memoriesApi } from "@/lib/api-client";
import type { MemoryResponse } from "@/lib/types";

export default function SettingsPage() {
  const [memories, setMemories] = useState<MemoryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profileEmail, setProfileEmail] = useState("user@example.com");

  const fetchMemories = useCallback(async () => {
    setLoading(true);
    try { const data = await memoriesApi.list(); setMemories(data.memories); }
    catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchMemories(); }, [fetchMemories]);

  const handleToggle = useCallback(async (id: string, active: boolean) => {
    try { await memoriesApi.update(id, { is_active: active }); setMemories(p => p.map(m => m.id === id ? { ...m, is_active: active } : m)); }
    catch {}
  }, []);

  const handleEdit = useCallback(async (id: string, content: string) => {
    try { await memoriesApi.update(id, { content }); setMemories(p => p.map(m => m.id === id ? { ...m, content } : m)); }
    catch {}
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    try { await memoriesApi.delete(id); setMemories(p => p.filter(m => m.id !== id)); }
    catch {}
  }, []);

  return (
    <ProtectedLayout>
      <TopBar title="Settings" />
      <div className="space-y-8 max-w-2xl">
        {/* Profile */}
        <section>
          <h2 className="text-[13px] font-semibold text-text-tertiary uppercase tracking-wider mb-3">Profile</h2>
          <Card>
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-pill bg-apple-blue flex items-center justify-center text-white font-bold text-[20px]">U</div>
              <div className="flex-1">
                <p className="text-[17px] font-medium text-text-primary">User</p>
                <p className="text-[15px] text-text-secondary">{profileEmail}</p>
              </div>
            </div>
          </Card>
        </section>

        {/* Memories */}
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[13px] font-semibold text-text-tertiary uppercase tracking-wider">Memories</h2>
          </div>
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : memories.length === 0 ? (
            <EmptyState title="No memories yet" description="Memories let the AI remember facts, preferences, and goals." />
          ) : (
            <div className="space-y-3">
              {memories.map(m => <MemoryCard key={m.id} memory={m} onToggleActive={handleToggle} onEdit={handleEdit} onDelete={handleDelete} />)}
            </div>
          )}
        </section>
      </div>
    </ProtectedLayout>
  );
}
