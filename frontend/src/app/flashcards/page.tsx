"use client";
import React, { useState, useEffect, useCallback } from "react";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { FlashcardCard } from "@/components/flashcards/FlashcardCard";
import { useToast } from "@/components/ui/Toast";
import { flashcardsApi } from "@/lib/api-client";
import { useDocuments } from "@/context/DocumentContext";
import type { FlashcardResponse } from "@/lib/types";
import { Layers, ChevronLeft, ChevronRight, Plus } from "lucide-react";

export default function FlashcardsPage() {
  const { documents } = useDocuments();
  const [flashcards, setFlashcards] = useState<FlashcardResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [currentIndex, setCurrentIndex] = useState(0);
  const { toast } = useToast();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const flashRes = await flashcardsApi.list({ page_size: 100 });
      setFlashcards(flashRes.flashcards);
    } catch (err) {
      console.error("[FlashcardsPage] fetchData:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleGenerate = useCallback(async () => {
    if (!selectedDocId) return;
    setGenerating(true);
    try {
      const res = await flashcardsApi.generate(selectedDocId);
      toast(res.message);
      fetchData();
      setSelectedDocId("");
    } catch {
      toast("Failed to generate flashcards", "error");
    } finally {
      setGenerating(false);
    }
  }, [selectedDocId, fetchData, toast]);

  const handleUpdate = useCallback(async (id: string, data: { front?: string; back?: string }) => {
    try {
      await flashcardsApi.update(id, data);
      setFlashcards(prev => prev.map(f => f.id === id ? { ...f, ...data } : f));
      toast("Flashcard updated");
    } catch {
      toast("Failed to update", "error");
    }
  }, [toast]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await flashcardsApi.delete(id);
      setFlashcards(prev => prev.filter(f => f.id !== id));
      if (currentIndex >= flashcards.length - 1) setCurrentIndex(Math.max(0, flashcards.length - 2));
      toast("Flashcard deleted");
    } catch {
      toast("Failed to delete", "error");
    }
  }, [currentIndex, flashcards.length, toast]);

  return (
    <ProtectedLayout>
      <TopBar
        title="Flashcards"
        subtitle={flashcards.length > 0 ? `${flashcards.length} cards total` : undefined}
      />

      {/* Generate */}
      <Card className="p-6 mb-8">
        <h3 className="text-title-md text-ink mb-4">Generate from Document</h3>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-caption text-ink-muted mb-1.5">Select a document</label>
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="input-airbnb"
            >
              <option value="">Choose a document...</option>
              {documents.map(doc => (
                <option key={doc.id} value={doc.id}>{doc.original_filename}</option>
              ))}
            </select>
          </div>
          <Button
            onClick={handleGenerate}
            loading={generating}
            disabled={!selectedDocId}
            icon={<Plus className="w-4 h-4" />}
          >
            Generate
          </Button>
        </div>
      </Card>

      {loading ? (
        <div className="max-w-lg mx-auto">
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      ) : flashcards.length === 0 ? (
        <EmptyState
          title="No flashcards yet"
          description="Generate flashcards from your documents to start studying."
          icon={<Layers className="w-8 h-8" />}
        />
      ) : (
        <div className="max-w-lg mx-auto">
          {/* Navigation */}
          <div className="flex items-center justify-between mb-6">
            <button
              onClick={() => setCurrentIndex(i => Math.max(0, i - 1))}
              disabled={currentIndex === 0}
              className="w-10 h-10 rounded-full flex items-center justify-center border border-border hover:border-ink transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-5 h-5 text-ink" />
            </button>
            <span className="text-body-sm text-ink-muted font-medium">
              {currentIndex + 1} / {flashcards.length}
            </span>
            <button
              onClick={() => setCurrentIndex(i => Math.min(flashcards.length - 1, i + 1))}
              disabled={currentIndex >= flashcards.length - 1}
              className="w-10 h-10 rounded-full flex items-center justify-center border border-border hover:border-ink transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-5 h-5 text-ink" />
            </button>
          </div>

          {/* Card */}
          <FlashcardCard
            key={flashcards[currentIndex].id}
            flashcard={flashcards[currentIndex]}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
          />

          {/* Keyboard hint */}
          <p className="text-center text-caption-sm text-ink-muted-soft mt-6">
            Click card to flip &middot; Use arrows to navigate
          </p>
        </div>
      )}
    </ProtectedLayout>
  );
}
