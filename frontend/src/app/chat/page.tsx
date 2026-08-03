"use client";
import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { chatApi } from "@/lib/api-client";
import type { ConversationSummary } from "@/lib/types";
import { MessageCircle, Plus } from "lucide-react";

export default function ChatPage() {
  const router = useRouter();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchConversations = useCallback(async () => {
    try {
      const res = await chatApi.listConversations(100, 0);
      setConversations(res.conversations);
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const handleNew = useCallback(async () => {
    try {
      const conv = await chatApi.createConversation();
      router.push(`/chat/${conv.id}`);
    } catch {}
  }, [router]);

  const handleSelect = useCallback(
    (id: string) => {
      router.push(`/chat/${id}`);
    },
    [router]
  );

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
  };

  return (
    <ProtectedLayout>
      <TopBar
        title="Chat"
        subtitle="Have conversations with your documents"
        rightAction={
          <Button onClick={handleNew} icon={<Plus className="w-4 h-4" />}>
            New Chat
          </Button>
        }
      />

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-32 rounded-xl skeleton" />
          ))}
        </div>
      ) : conversations.length === 0 ? (
        <EmptyState
          title="No conversations yet"
          description="Start a new chat to ask questions about your documents."
          icon={<MessageCircle className="w-8 h-8" />}
          action={
            <Button onClick={handleNew} icon={<Plus className="w-4 h-4" />}>
              Start Chat
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {conversations.map((c, i) => (
            <Card
              key={c.id}
              hover
              onClick={() => handleSelect(c.id)}
              className="p-5 animate-fade-in-up"
              style={{ animationDelay: `${i * 50}ms` } as React.CSSProperties}
            >
              <div className="flex items-start gap-3 mb-3">
                <div className="w-10 h-10 rounded-lg bg-rausch-light flex items-center justify-center flex-shrink-0">
                  <MessageCircle className="w-5 h-5 text-rausch" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-title-md text-ink truncate">
                    {c.title || "Untitled"}
                  </h3>
                  <p className="text-caption-sm text-ink-muted-soft mt-0.5">
                    {formatTime(c.updated_at)}
                  </p>
                </div>
              </div>
              <p className="text-body-sm text-ink-muted">
                {c.message_count} message{c.message_count !== 1 ? "s" : ""}
              </p>
            </Card>
          ))}
        </div>
      )}
    </ProtectedLayout>
  );
}
