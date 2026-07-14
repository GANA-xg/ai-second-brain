"use client";
import React from "react";
import { clsx } from "clsx";
import type { AttemptAnswerResult } from "@/lib/types";

interface QuizResultProps { score: number; totalQuestions: number; correctAnswers: number; results: AttemptAnswerResult[]; }

export function QuizResult({ score, totalQuestions, correctAnswers, results }: QuizResultProps) {
  const pct=totalQuestions>0?Math.round((correctAnswers/totalQuestions)*100):0;
  const gradeColor=pct>=80?"text-apple-green":pct>=60?"text-apple-yellow":"text-apple-red";
  const gradeRing=pct>=80?"stroke-apple-green":pct>=60?"stroke-apple-yellow":"stroke-apple-red";
  const radius=54; const circ=2*Math.PI*radius; const off=circ-(pct/100)*circ;

  return (
    <div className="w-full max-w-2xl mx-auto animate-slide-up">
      <div className="flex flex-col items-center mb-10">
        <div className="relative w-36 h-36 mb-4">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
            <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
            <circle cx="60" cy="60" r={radius} fill="none" stroke="currentColor" strokeWidth="8" strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off} className={clsx("transition-all duration-700 ease-out",gradeRing)} />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={clsx("text-[34px] font-bold",gradeColor)}>{pct}%</span>
            <span className="text-[13px] text-text-tertiary mt-0.5">{correctAnswers}/{totalQuestions}</span>
          </div>
        </div>
        <h2 className="text-[28px] font-semibold text-text-primary mb-1">{pct>=80?"Great job!":pct>=60?"Good effort!":"Keep practicing!"}</h2>
        <p className="text-[15px] text-text-tertiary">Score: {score.toFixed(1)} points</p>
      </div>
      <div className="space-y-3">
        <h3 className="text-[13px] font-semibold text-text-tertiary uppercase tracking-wider">Question Breakdown</h3>
        {results.map((r,idx)=><div key={idx} className={clsx("p-4 rounded-lg border transition-all",r.is_correct?"bg-apple-green/10 border-apple-green/20":"bg-apple-red/10 border-apple-red/20")}>
          <div className="flex items-start gap-3">
            <div className={clsx("flex-shrink-0 w-7 h-7 rounded-pill flex items-center justify-center text-[13px] font-bold mt-0.5",r.is_correct?"bg-apple-green/20 text-apple-green":"bg-apple-red/20 text-apple-red")}>{r.is_correct?"✓":"✗"}</div>
            <div className="flex-1 min-w-0">
              <p className="text-[15px] font-medium text-text-primary mb-2">{idx+1}. {r.question_text}</p>
              <div className="space-y-1 text-[15px]">
                <p className="text-text-secondary"><span className="font-medium">Your answer:</span> <span className={r.is_correct?"text-apple-green":"text-apple-red"}>{r.user_answer}</span></p>
                {!r.is_correct&&<p className="text-text-secondary"><span className="font-medium">Correct answer:</span> <span className="text-apple-green">{r.correct_answer}</span></p>}
              </div>
              {r.explanation&&<div className="mt-2 pt-2 border-t border-white/10"><p className="text-[13px] text-text-tertiary leading-relaxed">{r.explanation}</p></div>}
            </div>
          </div>
        </div>)}
      </div>
    </div>
  );
}
