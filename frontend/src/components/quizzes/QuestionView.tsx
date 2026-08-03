"use client";
import React, { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import type { QuizQuestionSchema } from "@/lib/types";

interface QuestionViewProps {
  question: QuizQuestionSchema;
  index: number;
  total: number;
  onAnswer: (questionId: string, answer: string) => void;
  selectedAnswer?: string;
  showResult?: boolean;
  isCorrect?: boolean;
}

export function QuestionView({ question, index, total, onAnswer, selectedAnswer, showResult, isCorrect }: QuestionViewProps) {
  const [shortAnswer, setShortAnswer] = useState("");

  const handleSelect = useCallback((answer: string) => {
    onAnswer(question.id, answer);
  }, [question.id, onAnswer]);

  const handleSubmitShort = useCallback(() => {
    if (shortAnswer.trim()) {
      onAnswer(question.id, shortAnswer.trim());
    }
  }, [question.id, shortAnswer, onAnswer]);

  return (
    <div className="animate-fade-in-up">
      {/* Progress */}
      <div className="flex items-center gap-3 mb-6">
        <span className="text-caption-sm text-ink-muted-soft">
          Question {index + 1} of {total}
        </span>
        <div className="flex-1 h-1 bg-canvas-strong rounded-full overflow-hidden">
          <div
            className="h-full bg-rausch rounded-full transition-all duration-300"
            style={{ width: `${((index + 1) / total) * 100}%` }}
          />
        </div>
      </div>

      {/* Question */}
      <h3 className="text-display-sm text-ink mb-6 leading-relaxed">
        {question.question_text}
      </h3>

      {/* Options */}
      {question.question_type === "multiple_choice" && question.options && (
        <div className="space-y-3">
          {question.options.map((option, i) => {
            const isSelected = selectedAnswer === option;
            const letter = String.fromCharCode(65 + i);

            return (
              <button
                key={i}
                onClick={() => !showResult && handleSelect(option)}
                disabled={showResult}
                className={cn(
                  "w-full flex items-center gap-3 p-4 rounded-xl border text-left transition-all duration-200",
                  showResult
                    ? option === question.correct_answer
                      ? "bg-success-light border-success/30"
                      : isSelected && option !== question.correct_answer
                      ? "bg-rausch-light border-rausch/30"
                      : "bg-canvas-soft border-border opacity-50"
                    : isSelected
                    ? "bg-rausch-light border-rausch shadow-glow"
                    : "bg-canvas border-border hover:border-border-strong hover:shadow-card"
                )}
              >
                <span className={cn(
                  "w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-body-sm font-medium",
                  showResult
                    ? option === question.correct_answer
                      ? "bg-success text-white"
                      : isSelected
                      ? "bg-error text-white"
                      : "bg-canvas-strong text-ink-muted"
                    : isSelected
                    ? "bg-rausch text-white"
                    : "bg-canvas-soft text-ink-muted"
                )}>
                  {showResult ? (
                    option === question.correct_answer ? "✓" : isSelected ? "✗" : letter
                  ) : letter}
                </span>
                <span className={cn(
                  "text-body-md",
                  showResult
                    ? option === question.correct_answer
                      ? "text-success font-medium"
                      : "text-ink-muted"
                    : "text-ink"
                )}>
                  {option}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {question.question_type === "true_false" && (
        <div className="flex gap-4">
          {["True", "False"].map((option) => {
            const isSelected = selectedAnswer === option;
            return (
              <button
                key={option}
                onClick={() => !showResult && handleSelect(option)}
                disabled={showResult}
                className={cn(
                  "flex-1 p-4 rounded-xl border text-body-md font-medium transition-all duration-200",
                  showResult
                    ? option === question.correct_answer
                      ? "bg-success-light border-success/30 text-success"
                      : isSelected
                      ? "bg-rausch-light border-rausch/30 text-error"
                      : "bg-canvas-soft border-border text-ink-muted opacity-50"
                    : isSelected
                    ? "bg-rausch-light border-rausch text-ink shadow-glow"
                    : "bg-canvas border-border text-ink hover:border-border-strong hover:shadow-card"
                )}
              >
                {option}
              </button>
            );
          })}
        </div>
      )}

      {question.question_type === "short_answer" && (
        <div className="space-y-3">
          <input
            type="text"
            value={shortAnswer}
            onChange={(e) => setShortAnswer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmitShort()}
            disabled={showResult}
            placeholder="Type your answer..."
            className="input-airbnb"
          />
          {!showResult && (
            <button
              onClick={handleSubmitShort}
              disabled={!shortAnswer.trim()}
              className="px-6 py-2.5 rounded-full bg-rausch text-white text-body-sm font-medium hover:bg-rausch-active transition-colors disabled:opacity-50"
            >
              Submit
            </button>
          )}
        </div>
      )}

      {/* Explanation */}
      {showResult && question.explanation && (
        <div className="mt-6 p-4 rounded-xl bg-canvas-soft border border-border animate-fade-in">
          <p className="text-caption text-ink font-medium mb-1">Explanation</p>
          <p className="text-body-sm text-ink-muted">{question.explanation}</p>
        </div>
      )}
    </div>
  );
}
