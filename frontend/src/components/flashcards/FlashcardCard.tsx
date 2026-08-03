"use client";
import React, { useState, useCallback } from "react";
import type { FlashcardResponse } from "@/lib/types";
import { Badge } from "@/components/ui/Badge";

interface FlashcardCardProps {
  flashcard: FlashcardResponse;
  onUpdate?: (id: string, data: { front?: string; back?: string }) => void;
  onDelete?: (id: string) => void;
}

export function FlashcardCard({ flashcard, onUpdate, onDelete }: FlashcardCardProps) {
  const [flipped, setFlipped] = useState(false);
  const [editing, setEditing] = useState(false);
  const [front, setFront] = useState(flashcard.front);
  const [back, setBack] = useState(flashcard.back);

  const handleSave = useCallback(() => {
    onUpdate?.(flashcard.id, { front, back });
    setEditing(false);
  }, [flashcard.id, front, back, onUpdate]);

  const difficultyColor = {
    easy: "success" as const,
    medium: "warning" as const,
    hard: "danger" as const,
  };

  return (
    <div
      className="cursor-pointer"
      style={{ perspective: "1000px" }}
      onClick={() => !editing && setFlipped(!flipped)}
    >
      <div
        className="relative w-full min-h-[240px] transition-transform duration-500"
        style={{ transformStyle: "preserve-3d", transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)" }}
      >
        {/* Front */}
        <div
          className="absolute inset-0 bg-canvas border border-border rounded-xl p-6 flex flex-col"
          style={{ backfaceVisibility: "hidden" }}
        >
          <div className="flex items-center justify-between mb-4">
            <Badge variant={difficultyColor[flashcard.difficulty]}>
              {flashcard.difficulty}
            </Badge>
            <span className="text-caption-sm text-ink-muted-soft">Front</span>
          </div>
          {editing ? (
            <textarea
              value={front}
              onChange={(e) => setFront(e.target.value)}
              className="flex-1 bg-canvas-soft border border-border rounded-lg p-3 text-body-md text-ink outline-none resize-none focus:border-ink"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <p className="flex-1 text-body-md text-ink leading-relaxed">{flashcard.front}</p>
          )}
        </div>

        {/* Back */}
        <div
          className="absolute inset-0 bg-canvas-soft border border-border rounded-xl p-6 flex flex-col"
          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
        >
          <div className="flex items-center justify-between mb-4">
            <span className="text-caption text-ink-muted uppercase tracking-wider">Answer</span>
          </div>
          {editing ? (
            <textarea
              value={back}
              onChange={(e) => setBack(e.target.value)}
              className="flex-1 bg-canvas border border-border rounded-lg p-3 text-body-md text-ink outline-none resize-none focus:border-ink"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <p className="flex-1 text-body-md text-ink leading-relaxed">{flashcard.back}</p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-center gap-2 mt-4">
        {editing ? (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); handleSave(); }}
              className="px-4 py-1.5 rounded-full bg-rausch text-white text-body-sm font-medium hover:bg-rausch-active transition-colors"
            >
              Save
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setEditing(false); setFront(flashcard.front); setBack(flashcard.back); }}
              className="px-4 py-1.5 rounded-full bg-canvas-soft text-ink text-body-sm font-medium hover:bg-canvas-strong transition-colors"
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            <button
              onClick={(e) => { e.stopPropagation(); setEditing(true); }}
              className="px-4 py-1.5 rounded-full bg-canvas-soft text-ink text-body-sm font-medium hover:bg-canvas-strong transition-colors"
            >
              Edit
            </button>
            {onDelete && (
              <button
                onClick={(e) => { e.stopPropagation(); onDelete(flashcard.id); }}
                className="px-4 py-1.5 rounded-full text-error text-body-sm font-medium hover:bg-rausch-light transition-colors"
              >
                Delete
              </button>
            )}
          </>
        )}
      </div>
    </div>
  );
}
