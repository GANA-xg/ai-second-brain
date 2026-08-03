"use client";
import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { quizzesApi } from "@/lib/api-client";
import { useDocuments } from "@/context/DocumentContext";
import type { QuizSummary } from "@/lib/types";
import { HelpCircle, Plus, Trash2 } from "lucide-react";

export default function QuizzesPage() {
  const { documents } = useDocuments();
  const router = useRouter();
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const { toast } = useToast();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const quizzesRes = await quizzesApi.list({ page_size: 100 });
      setQuizzes(quizzesRes.quizzes);
    } catch (err) {
      console.error("[QuizzesPage] fetchData:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleGenerate = useCallback(async () => {
    if (!selectedDocId) return;
    setGenerating(true);
    try {
      const res = await quizzesApi.generate(selectedDocId);
      toast(res.message);
      fetchData();
      setSelectedDocId("");
    } catch {
      toast("Failed to generate quiz", "error");
    } finally {
      setGenerating(false);
    }
  }, [selectedDocId, fetchData, toast]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await quizzesApi.delete(id);
      setQuizzes(prev => prev.filter(q => q.id !== id));
      toast("Quiz deleted");
    } catch {
      toast("Failed to delete", "error");
    }
  }, [toast]);

  return (
    <ProtectedLayout>
      <TopBar title="Quizzes" subtitle="Test your knowledge" />

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

      {/* Quiz List */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : quizzes.length === 0 ? (
        <EmptyState
          title="No quizzes yet"
          description="Generate a quiz from a document to get started."
          icon={<HelpCircle className="w-8 h-8" />}
        />
      ) : (
        <div className="space-y-3">
          {quizzes.map((quiz, i) => (
            <Card
              key={quiz.id}
              hover
              onClick={() => router.push(`/quizzes/${quiz.id}`)}
              className="p-5 flex items-center gap-4 animate-fade-in-up"
              style={{ animationDelay: `${i * 50}ms` } as React.CSSProperties}
            >
              <div className="w-12 h-12 rounded-xl bg-rausch-light flex items-center justify-center flex-shrink-0">
                <HelpCircle className="w-6 h-6 text-rausch" />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-title-md text-ink truncate">{quiz.title}</h3>
                <p className="text-caption-sm text-ink-muted-soft">
                  {quiz.total_questions} questions &middot; {new Date(quiz.created_at).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(quiz.id); }}
                className="w-8 h-8 rounded-full flex items-center justify-center text-ink-muted hover:bg-rausch-light hover:text-error transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </Card>
          ))}
        </div>
      )}
    </ProtectedLayout>
  );
}
