"use client";
import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { quizzesApi } from "@/lib/api-client";
import type { QuizSummary } from "@/lib/types";

export default function QuizzesPage() {
  const router=useRouter();
  const [quizzes, setQuizzes]=useState<QuizSummary[]>([]);
  const [loading, setLoading]=useState(true);
  const [generating, setGenerating]=useState(false);
  const [topic, setTopic]=useState("");

  const fetchQuizzes=useCallback(async()=>{
    setLoading(true);
    try{const data=await quizzesApi.list();setQuizzes(data.quizzes);}catch{}
    finally{setLoading(false);}
  },[]);
  useEffect(()=>{fetchQuizzes();},[fetchQuizzes]);

  const handleGenerate=useCallback(async()=>{
    if(!topic.trim())return;setGenerating(true);
    try{const data=await quizzesApi.generate(topic.trim());router.push(`/quizzes/${data.quiz_id}`);}
    catch{}finally{setGenerating(false);}
  },[topic,router]);

  const handleDelete=useCallback(async(id:string)=>{try{await quizzesApi.delete(id);setQuizzes(p=>p.filter(q=>q.id!==id));}catch{}},[setQuizzes]);

  return <ProtectedLayout><TopBar title="Quizzes" />
    <div className="flex items-end gap-3 mb-8">
      <div className="flex-1"><Input value={topic} onChange={e=>setTopic(e.target.value)} onKeyDown={e=>e.key==="Enter"&&handleGenerate()} placeholder="Enter a topic…" /></div>
      <Button onClick={handleGenerate} loading={generating}>Generate Quiz</Button>
    </div>
    {loading?<div className="space-y-3">{[1,2].map(i=><Skeleton key={i} className="h-24 w-full" />)}</div>
    :quizzes.length===0?<EmptyState title="No quizzes yet" description="Generate your first quiz above." />
    :<div className="space-y-3">{quizzes.map(q=><Card key={q.id} hover onClick={()=>router.push(`/quizzes/${q.id}`)}>
      <div className="flex items-center justify-between">
        <div><p className="text-[17px] font-medium text-text-primary">{q.title}</p><p className="text-[13px] text-text-tertiary mt-0.5">{q.total_questions} questions</p></div>
        <button onClick={e=>{e.stopPropagation();handleDelete(q.id);}} className="text-text-tertiary hover:text-apple-red transition-colors p-1" aria-label="Delete quiz"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg></button>
      </div>
    </Card>)}</div>}
  </ProtectedLayout>;
}
