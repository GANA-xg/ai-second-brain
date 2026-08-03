"use client";
import React from "react";
import { cn } from "@/lib/utils";
import type { QuizAttemptResponse } from "@/lib/types";
import { CheckCircle, XCircle } from "lucide-react";

interface QuizResultProps {
  result: QuizAttemptResponse;
  onRetry?: () => void;
  onBack?: () => void;
}

export function QuizResult({ result, onRetry, onBack }: QuizResultProps) {
  const percentage = Math.round((result.score / result.total_questions) * 100);

  const getGrade = () => {
    if (percentage >= 90) return { label: "Excellent!", color: "text-success" };
    if (percentage >= 70) return { label: "Good job!", color: "text-info" };
    if (percentage >= 50) return { label: "Keep trying!", color: "text-warning" };
    return { label: "Needs practice", color: "text-error" };
  };

  const grade = getGrade();

  return (
    <div className="animate-fade-in-up">
      {/* Score Ring */}
      <div className="flex flex-col items-center mb-10">
        <div className="relative w-32 h-32 mb-4">
          <svg className="w-32 h-32 -rotate-90" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r="52" fill="none" stroke="var(--canvas-strong)" strokeWidth="8" />
            <circle
              cx="60"
              cy="60"
              r="52"
              fill="none"
              stroke={percentage >= 70 ? "var(--success)" : percentage >= 50 ? "var(--warning)" : "var(--error)"}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${2 * Math.PI * 52}`}
              strokeDashoffset={`${2 * Math.PI * 52 * (1 - percentage / 100)}`}
              className="transition-all duration-1000 ease-out"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-hero-sm text-ink font-bold">{percentage}%</span>
          </div>
        </div>
        <h2 className={cn("text-display-md", grade.color)}>{grade.label}</h2>
        <p className="text-body-md text-ink-muted mt-1">
          {result.correct_answers} of {result.total_questions} correct
        </p>
      </div>

      {/* Breakdown */}
      <div className="space-y-3 mb-8">
        {result.results.map((r, i) => (
          <div
            key={i}
            className={cn(
              "flex items-start gap-3 p-4 rounded-xl border",
              r.is_correct
                ? "bg-success-light border-success/20"
                : "bg-rausch-light border-rausch/20"
            )}
          >
            {r.is_correct ? (
              <CheckCircle className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
            ) : (
              <XCircle className="w-5 h-5 text-error flex-shrink-0 mt-0.5" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-body-sm text-ink font-medium mb-1">{r.question_text}</p>
              <p className="text-caption-sm text-ink-muted">
                Your answer: <span className={r.is_correct ? "text-success" : "text-error"}>{r.user_answer}</span>
              </p>
              {!r.is_correct && (
                <p className="text-caption-sm text-success mt-0.5">
                  Correct: {r.correct_answer}
                </p>
              )}
              {r.explanation && (
                <p className="text-caption-sm text-ink-muted-soft mt-1 italic">{r.explanation}</p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-center gap-3">
        {onBack && (
          <button
            onClick={onBack}
            className="px-6 py-2.5 rounded-full bg-canvas-soft text-ink text-body-sm font-medium hover:bg-canvas-strong transition-colors"
          >
            Back to Quizzes
          </button>
        )}
        {onRetry && (
          <button
            onClick={onRetry}
            className="px-6 py-2.5 rounded-full bg-rausch text-white text-body-sm font-medium hover:bg-rausch-active transition-colors"
          >
            Try Again
          </button>
        )}
      </div>
    </div>
  );
}
