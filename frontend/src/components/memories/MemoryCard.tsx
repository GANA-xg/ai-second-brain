"use client";
import React, { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import type { MemoryResponse } from "@/lib/types";
import { Trash2, Pencil, Check, X, Brain, Star, Target } from "lucide-react";

interface MemoryCardProps {
  memory: MemoryResponse;
  onUpdate?: (id: string, data: { content?: string; type?: string; is_active?: boolean }) => void;
  onDelete?: (id: string) => void;
}

export function MemoryCard({ memory, onUpdate, onDelete }: MemoryCardProps) {
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState(memory.content);

  const handleSave = useCallback(() => {
    onUpdate?.(memory.id, { content: editContent });
    setEditing(false);
  }, [memory.id, editContent, onUpdate]);

  const typeConfig = {
    FACT: { icon: Brain, color: "text-info", bg: "bg-info-light", label: "Fact" },
    PREFERENCE: { icon: Star, color: "text-rausch", bg: "bg-rausch-light", label: "Preference" },
    GOAL: { icon: Target, color: "text-success", bg: "bg-success-light", label: "Goal" },
  };

  const config = typeConfig[memory.type] || typeConfig.FACT;
  const Icon = config.icon;

  return (
    <div className={cn(
      "group bg-canvas border border-border rounded-xl p-4 transition-all duration-200 hover:shadow-card",
      !memory.is_active && "opacity-50"
    )}>
      <div className="flex items-start gap-3">
        <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0", config.bg)}>
          <Icon className={cn("w-4 h-4", config.color)} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn("text-caption-sm font-medium", config.color)}>{config.label}</span>
            <span className="text-caption-sm text-ink-muted-soft">
              {Math.round(memory.confidence * 100)}% confidence
            </span>
          </div>
          {editing ? (
            <div className="flex items-start gap-2">
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="flex-1 bg-canvas-soft border border-border rounded-lg p-2 text-body-sm text-ink outline-none resize-none focus:border-ink min-h-[60px]"
                autoFocus
              />
              <div className="flex flex-col gap-1">
                <button onClick={handleSave} className="w-7 h-7 rounded flex items-center justify-center text-success hover:bg-success-light">
                  <Check className="w-4 h-4" />
                </button>
                <button onClick={() => { setEditing(false); setEditContent(memory.content); }} className="w-7 h-7 rounded flex items-center justify-center text-ink-muted hover:bg-canvas-soft">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
          ) : (
            <p className="text-body-sm text-ink">{memory.content}</p>
          )}
        </div>
        {!editing && (
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={() => setEditing(true)}
              className="w-7 h-7 rounded flex items-center justify-center text-ink-muted hover:bg-canvas-soft"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onDelete?.(memory.id)}
              className="w-7 h-7 rounded flex items-center justify-center text-ink-muted hover:bg-rausch-light hover:text-error"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
