"use client";
import React, { useCallback } from "react";
import { clsx } from "clsx";
import { Input } from "@/components/ui/Input";
import type { QuizQuestionSchema } from "@/lib/types";

interface QuestionViewProps {
  question: QuizQuestionSchema; selectedAnswer: string; onAnswer: (a:string)=>void;
  feedback?: { isCorrect: boolean; correctAnswer: string } | null;
  questionNumber: number; totalQuestions: number;
}

export function QuestionView({ question, selectedAnswer, onAnswer, feedback, questionNumber, totalQuestions }: QuestionViewProps) {
  const handleOptionClick=useCallback((o:string)=>{if(!feedback)onAnswer(o);},[onAnswer,feedback]);
  const typeLabel=question.question_type==="multiple_choice"?"Multiple Choice":question.question_type==="true_false"?"True or False":"Short Answer";
  const displayOptions=question.question_type==="true_false"?["True","False"]:question.options??[];

  return (
    <div className="w-full max-w-2xl mx-auto animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <span className="text-[15px] text-text-tertiary">Question {questionNumber} of {totalQuestions}</span>
        <span className="inline-flex items-center px-[10px] py-1 rounded-pill text-[13px] font-medium bg-apple-blue/15 text-apple-blue-on-dark">{typeLabel}</span>
      </div>
      <h2 className="text-[28px] font-semibold text-text-primary text-center leading-snug mb-8">{question.question_text}</h2>
      <div className="space-y-3">
        {(question.question_type==="multiple_choice"||question.question_type==="true_false")&&displayOptions.map(option=>{
          const isSelected=selectedAnswer===option;
          return <button key={option} onClick={()=>handleOptionClick(option)} disabled={!!feedback}
            className={clsx("w-full text-left px-5 py-4 rounded-lg border transition-all duration-150 hover:border-apple-blue/50 disabled:cursor-default",
              feedback?(option===feedback.correctAnswer?"border-apple-green bg-apple-green/10 text-apple-green":isSelected&&!feedback.isCorrect?"border-apple-red bg-apple-red/10 text-apple-red":"border-surface-border text-text-primary bg-surface-secondary"):
              isSelected?"border-apple-blue bg-apple-blue/15 text-apple-blue-on-dark":"border-surface-border bg-surface-secondary text-text-primary hover:bg-surface-card-hover")}>
            <span className="text-[17px] font-medium">{option}</span>
            {feedback&&option===feedback.correctAnswer&&<span className="float-right text-apple-green ml-2">✓ Correct</span>}
            {feedback&&isSelected&&!feedback.isCorrect&&<span className="float-right text-apple-red ml-2">✗ Incorrect</span>}
          </button>;
        })}
        {question.question_type==="short_answer"&&(
          <div className="space-y-2">
            <Input placeholder="Type your answer…" value={selectedAnswer} onChange={e=>!feedback&&onAnswer(e.target.value)} disabled={!!feedback} className={clsx(feedback&&"opacity-70")} />
            {feedback&&<div className={clsx("mt-2 p-3 rounded-lg text-[15px]",feedback.isCorrect?"bg-apple-green/10 text-apple-green border border-apple-green/20":"bg-apple-red/10 text-apple-red border border-apple-red/20")}>
              {feedback.isCorrect?<p>✓ Correct!</p>:<p>✗ Incorrect. Correct answer: <strong>{feedback.correctAnswer}</strong></p>}
            </div>}
          </div>
        )}
      </div>
      {feedback&&question.explanation&&<div className="mt-6 p-4 rounded-lg bg-surface-secondary border border-surface-border"><p className="text-[13px] font-semibold text-text-tertiary uppercase tracking-wider mb-1">Explanation</p><p className="text-[15px] text-text-secondary leading-relaxed">{question.explanation}</p></div>}
    </div>
  );
}
