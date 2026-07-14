"use client";
import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { clsx } from "clsx";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { Skeleton } from "@/components/ui/Skeleton";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuestionView } from "@/components/quizzes/QuestionView";
import { QuizResult } from "@/components/quizzes/QuizResult";
import { quizzesApi } from "@/lib/api-client";
import type { QuizResponse, QuizQuestionSchema, AttemptAnswerResult, AttemptSummary } from "@/lib/types";

export default function QuizDetailPage() {
  const params=useParams(); const router=useRouter();
  const quizId=params.id as string;
  const [quiz,setQuiz]=useState<QuizResponse|null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState<string|null>(null);
  const [currentIndex,setCurrentIndex]=useState(0);
  const [answers,setAnswers]=useState<Record<string,string>>({});
  const [submitting,setSubmitting]=useState(false);
  const [attemptResult,setAttemptResult]=useState<{id:string;score:number;totalQuestions:number;correctAnswers:number;results:AttemptAnswerResult[]}|null>(null);
  const [attemptHistory,setAttemptHistory]=useState<AttemptSummary[]>([]);
  const [historyLoading,setHistoryLoading]=useState(true);

  const fetchQuiz=useCallback(async()=>{setLoading(true);setError(null);try{setQuiz(await quizzesApi.get(quizId));}catch{setError("Failed to load quiz.");}finally{setLoading(false);}},[quizId]);
  const fetchHistory=useCallback(async()=>{setHistoryLoading(true);try{const d=await quizzesApi.listAttempts(quizId);setAttemptHistory(d.attempts);}catch{}finally{setHistoryLoading(false);}},[quizId]);

  useEffect(()=>{fetchQuiz();fetchHistory();},[fetchQuiz,fetchHistory]);

  const handleAnswer=useCallback((a:string)=>{if(!quiz)return;const q=quiz.questions[currentIndex];setAnswers(p=>({...p,[q.id]:a}));},[quiz,currentIndex]);
  const goNext=useCallback(()=>{if(!quiz||currentIndex>=quiz.questions.length-1)return;setCurrentIndex(p=>p+1);},[quiz,currentIndex]);
  const goPrev=useCallback(()=>{if(currentIndex>0)setCurrentIndex(p=>p-1);},[currentIndex]);

  const handleSubmit=useCallback(async()=>{if(!quiz)return;setSubmitting(true);
    try{const arr=Object.entries(answers).map(([qid,ans])=>({question_id:qid,answer:ans}));const r=await quizzesApi.submitAttempt(quizId,arr);
      setAttemptResult({id:r.id,score:r.score,totalQuestions:r.total_questions,correctAnswers:r.correct_answers,results:r.results});await fetchHistory();}
    catch{}finally{setSubmitting(false);}},[quiz,answers,quizId,fetchHistory]);

  const handleRetry=useCallback(()=>{setAnswers({});setCurrentIndex(0);setAttemptResult(null);},[]);

  const totalQuestions=quiz?.questions.length??0;
  const answeredCount=Object.keys(answers).length;
  const allAnswered=answeredCount===totalQuestions&&totalQuestions>0;
  const currentQuestion=quiz?.questions[currentIndex]??null;

  if(loading)return <ProtectedLayout><TopBar title="Quiz" showBack /><div className="space-y-4 max-w-2xl mx-auto mt-8"><Skeleton className="h-6 w-48" /><Skeleton className="h-12 w-full" /><Skeleton className="h-40 w-full" /></div></ProtectedLayout>;
  if(error||!quiz)return <ProtectedLayout><TopBar title="Quiz" showBack /><EmptyState title="Quiz not found" description={error??"This quiz could not be loaded."} action={<Button variant="secondary" onClick={()=>router.push("/quizzes")}>Back to Quizzes</Button>} /></ProtectedLayout>;

  if(attemptResult)return <ProtectedLayout><TopBar title={quiz.title} showBack rightAction={<Button variant="secondary" size="sm" onClick={handleRetry}>Retry Quiz</Button>} />
    <div className="space-y-10">
      <QuizResult score={attemptResult.score} totalQuestions={attemptResult.totalQuestions} correctAnswers={attemptResult.correctAnswers} results={attemptResult.results} />
      <div className="w-full max-w-2xl mx-auto">
        <h3 className="text-[13px] font-semibold text-text-tertiary uppercase tracking-wider mb-3">Attempt History</h3>
        {historyLoading?<Skeleton className="h-14 w-full" />
        :attemptHistory.length===0?<p className="text-[15px] text-text-tertiary">No previous attempts.</p>
        :<div className="space-y-2">{attemptHistory.map(a=>{const p=a.total_questions>0?Math.round((a.correct_answers/a.total_questions)*100):0;
          return <Card key={a.id} className="p-4"><div className="flex items-center justify-between"><div><p className="text-[15px] font-medium text-text-primary">{a.correct_answers}/{a.total_questions} correct</p><p className="text-[13px] text-text-tertiary mt-0.5">{a.completed_at?new Date(a.completed_at).toLocaleDateString(undefined,{month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}):"In progress…"}</p></div><Badge variant={p>=80?"success":p>=60?"warning":"danger"}>{p}%</Badge></div></Card>;})}</div>}
      </div>
    </div>
  </ProtectedLayout>;

  return <ProtectedLayout><TopBar title={quiz.title} showBack />
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-center gap-2 mb-8">{quiz.questions.map((q,idx)=>{const isA=q.id in answers;const isC=idx===currentIndex;
        return <button key={q.id} onClick={()=>setCurrentIndex(idx)} className={clsx("w-8 h-8 rounded-pill flex items-center justify-center text-[13px] font-medium transition-all duration-150",
          isC?"bg-apple-blue text-white":isA?"bg-apple-blue/15 text-apple-blue-on-dark border border-apple-blue/30":"bg-white/5 text-text-tertiary border border-white/10 hover:border-white/20")} title={`Question ${idx+1}${isA?" (answered)":""}`}>{idx+1}</button>;})}
      </div>
      {currentQuestion&&<div className="animate-fade-in">
        <QuestionView question={currentQuestion} selectedAnswer={answers[currentQuestion.id]??""} onAnswer={handleAnswer} questionNumber={currentIndex+1} totalQuestions={totalQuestions} />
        <div className="flex items-center justify-between mt-8 pt-6 border-t border-surface-border">
          <Button variant="ghost" onClick={goPrev} disabled={currentIndex===0}><svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" /></svg>Previous</Button>
          {currentIndex<totalQuestions-1?<Button onClick={goNext} disabled={!(currentQuestion.id in answers)}>Next<svg className="w-4 h-4 ml-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" /></svg></Button>
          :<Button onClick={handleSubmit} loading={submitting} disabled={!allAnswered}>Submit Quiz<svg className="w-4 h-4 ml-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg></Button>}
        </div>
        <p className="text-center text-[13px] text-text-tertiary mt-4">{answeredCount} of {totalQuestions} questions answered{!allAnswered&&" (answer all to submit)"}</p>
      </div>}
      {!currentQuestion&&totalQuestions===0&&<EmptyState title="No questions" description="This quiz has no questions." />}
    </div>
  </ProtectedLayout>;
}
