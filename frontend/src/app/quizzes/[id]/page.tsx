"use client";
import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { QuestionView } from "@/components/quizzes/QuestionView";
import { QuizResult } from "@/components/quizzes/QuizResult";
import { quizzesApi } from "@/lib/api-client";
import type { QuizResponse, QuizAttemptResponse, AttemptSummary } from "@/lib/types";
import { ArrowLeft } from "lucide-react";

export default function QuizDetailPage() {
  const params = useParams();
  const router = useRouter();
  const quizId = params.id as string;

  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [result, setResult] = useState<QuizAttemptResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [attempts, setAttempts] = useState<AttemptSummary[]>([]);
  const [showAttempts, setShowAttempts] = useState(false);

  const fetchQuiz = useCallback(async () => {
    setLoading(true);
    try {
      const data = await quizzesApi.get(quizId);
      setQuiz(data);
      const attemptsRes = await quizzesApi.listAttempts(quizId);
      setAttempts(attemptsRes.attempts);
    } catch {
    } finally {
      setLoading(false);
    }
  }, [quizId]);

  useEffect(() => { fetchQuiz(); }, [fetchQuiz]);

  const handleAnswer = useCallback((questionId: string, answer: string) => {
    setAnswers(prev => ({ ...prev, [questionId]: answer }));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!quiz) return;
    setSubmitting(true);
    try {
      const answerArray = quiz.questions.map(q => ({
        question_id: q.id,
        answer: answers[q.id] || "",
      }));
      const res = await quizzesApi.submitAttempt(quizId, answerArray);
      setResult(res);
      setSubmitted(true);
    } catch {
    } finally {
      setSubmitting(false);
    }
  }, [quiz, answers, quizId]);

  const handleRetry = useCallback(() => {
    setAnswers({});
    setCurrentQuestion(0);
    setSubmitted(false);
    setResult(null);
  }, []);

  if (loading) return (
    <ProtectedLayout>
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    </ProtectedLayout>
  );

  if (!quiz) return (
    <ProtectedLayout>
      <div className="text-center py-16">
        <p className="text-body-md text-ink-muted">Quiz not found</p>
        <Button variant="secondary" className="mt-4" onClick={() => router.push("/quizzes")}>
          Back to Quizzes
        </Button>
      </div>
    </ProtectedLayout>
  );

  return (
    <ProtectedLayout>
      <TopBar
        title={quiz.title}
        backHref="/quizzes"
        rightAction={
          !submitted && (
            <span className="text-body-sm text-ink-muted">
              {Object.keys(answers).length} / {quiz.questions.length} answered
            </span>
          )
        }
      />

      {submitted && result ? (
        <QuizResult result={result} onRetry={handleRetry} onBack={() => router.push("/quizzes")} />
      ) : (
        <div className="max-w-2xl mx-auto">
          <QuestionView
            key={quiz.questions[currentQuestion].id}
            question={quiz.questions[currentQuestion]}
            index={currentQuestion}
            total={quiz.questions.length}
            onAnswer={handleAnswer}
            selectedAnswer={answers[quiz.questions[currentQuestion].id]}
          />

          {/* Navigation */}
          <div className="flex items-center justify-between mt-8">
            <Button
              variant="secondary"
              onClick={() => setCurrentQuestion(i => Math.max(0, i - 1))}
              disabled={currentQuestion === 0}
            >
              Previous
            </Button>

            {currentQuestion === quiz.questions.length - 1 ? (
              <Button
                onClick={handleSubmit}
                loading={submitting}
                disabled={Object.keys(answers).length < quiz.questions.length}
              >
                Submit Quiz
              </Button>
            ) : (
              <Button
                onClick={() => setCurrentQuestion(i => Math.min(quiz.questions.length - 1, i + 1))}
              >
                Next
              </Button>
            )}
          </div>

          {/* Question dots */}
          <div className="flex items-center justify-center gap-1.5 mt-6">
            {quiz.questions.map((q, i) => (
              <button
                key={q.id}
                onClick={() => setCurrentQuestion(i)}
                className={`w-2.5 h-2.5 rounded-full transition-all duration-200 ${
                  i === currentQuestion
                    ? "bg-rausch w-6"
                    : answers[q.id]
                    ? "bg-rausch/40"
                    : "bg-canvas-strong"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Previous Attempts */}
      {!submitted && attempts.length > 0 && (
        <div className="max-w-2xl mx-auto mt-12">
          <button
            onClick={() => setShowAttempts(!showAttempts)}
            className="text-body-sm text-rausch font-medium hover:underline"
          >
            {showAttempts ? "Hide" : "Show"} previous attempts ({attempts.length})
          </button>
          {showAttempts && (
            <div className="mt-3 space-y-2">
              {attempts.map((a) => (
                <div key={a.id} className="flex items-center justify-between p-3 bg-canvas-soft rounded-lg">
                  <span className="text-body-sm text-ink">
                    Score: {a.score}% ({a.correct_answers}/{a.total_questions})
                  </span>
                  <span className="text-caption-sm text-ink-muted-soft">
                    {new Date(a.created_at).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </ProtectedLayout>
  );
}
