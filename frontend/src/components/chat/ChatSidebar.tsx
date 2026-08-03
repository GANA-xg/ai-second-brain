"use client";
import React, { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import type { ConversationSummary } from "@/lib/types";
import { Plus, MessageCircle, Trash2, Pencil, Check, X, RefreshCw } from "lucide-react";
import { chatApi } from "@/lib/api-client";

interface ChatSidebarProps {
  conversations: ConversationSummary[];
  activeConversationId?: string;
  isLoading?: boolean;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onRefresh: () => void;
}

export function ChatSidebar({
  conversations,
  activeConversationId,
  isLoading,
  onNewConversation,
  onSelectConversation,
  onRefresh,
}: ChatSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const handleRename = useCallback(async (id: string) => {
    if (editValue.trim()) {
      try {
        await chatApi.updateConversation(id, editValue.trim());
        onRefresh();
      } catch {}
    }
    setEditingId(null);
  }, [editValue, onRefresh]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await chatApi.deleteConversation(id);
      onRefresh();
    } catch {}
  }, [onRefresh]);

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "now";
    if (diffMins < 60) return `${diffMins}m`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d`;
  };

  return (
    <div className="w-[260px] flex-shrink-0 border-r border-border bg-canvas-soft flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-caption text-ink-muted uppercase tracking-wider">Conversations</h2>
        <div className="flex items-center gap-1">
          <button
            onClick={onRefresh}
            className="w-7 h-7 rounded-full flex items-center justify-center hover:bg-canvas-strong transition-colors text-ink-muted"
            aria-label="Refresh"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onNewConversation}
            className="w-7 h-7 rounded-full flex items-center justify-center bg-rausch text-white hover:bg-rausch-active transition-colors"
            aria-label="New conversation"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {isLoading ? (
          <div className="space-y-1 px-2 py-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded-lg skeleton" />
            ))}
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-12 px-4">
            <MessageCircle className="w-8 h-8 text-ink-muted-soft mx-auto mb-3" />
            <p className="text-body-sm text-ink-muted">No conversations yet</p>
          </div>
        ) : (
          conversations.map((conv) => {
            const isActive = conv.id === activeConversationId;
            const isEditing = editingId === conv.id;

            return (
              <div
                key={conv.id}
                className={cn(
                  "group flex items-center gap-2 px-3 py-2.5 rounded-lg mb-0.5 transition-all duration-150",
                  isActive
                    ? "bg-canvas shadow-card border border-border"
                    : "hover:bg-canvas-soft/60 cursor-pointer"
                )}
                onClick={() => {
                  if (!isEditing) onSelectConversation(conv.id);
                }}
              >
                <MessageCircle
                  className={cn(
                    "w-4 h-4 flex-shrink-0",
                    isActive ? "text-rausch" : "text-ink-muted-soft"
                  )}
                />
                <div className="flex-1 min-w-0">
                  {isEditing ? (
                    <div className="flex items-center gap-1">
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleRename(conv.id);
                          if (e.key === "Escape") setEditingId(null);
                        }}
                        className="flex-1 bg-canvas border border-border rounded px-2 py-0.5 text-body-sm text-ink outline-none focus:border-ink"
                        autoFocus
                        onClick={(e) => e.stopPropagation()}
                      />
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRename(conv.id);
                        }}
                        className="w-5 h-5 rounded flex items-center justify-center text-success hover:bg-success-light"
                      >
                        <Check className="w-3 h-3" />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingId(null);
                        }}
                        className="w-5 h-5 rounded flex items-center justify-center text-ink-muted hover:bg-canvas-soft"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <p className={cn(
                        "text-body-sm truncate",
                        isActive ? "text-ink font-medium" : "text-ink"
                      )}>
                        {conv.title || "Untitled"}
                      </p>
                      <p className="text-caption-sm text-ink-muted-soft">
                        {conv.message_count} messages &middot; {formatTime(conv.updated_at)}
                      </p>
                    </>
                  )}
                </div>

                {!isEditing && (
                  <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingId(conv.id);
                        setEditValue(conv.title || "");
                      }}
                      className="w-6 h-6 rounded flex items-center justify-center hover:bg-canvas-soft text-ink-muted"
                      aria-label="Rename"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(conv.id);
                      }}
                      className="w-6 h-6 rounded flex items-center justify-center hover:bg-rausch-light text-ink-muted hover:text-error"
                      aria-label="Delete"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
