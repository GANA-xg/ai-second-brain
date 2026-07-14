"use client";
import React, { useState, useEffect, useCallback } from "react";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { FlashcardCard } from "@/components/flashcards/FlashcardCard";
import { flashcardsApi } from "@/lib/api-client";
import type { FlashcardDifficulty, FlashcardResponse } from "@/lib/types";

export default function FlashcardsPage() {
  const [flashcards, setFlashcards] = useState<FlashcardResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string|null>(null);
  const [currentIndex, setCurrentIndex]=useState(0);

  const fetchFlashcards=useCallback(async()=>{setLoading(true);setError(null);
    try{const data=await flashcardsApi.list();setFlashcards(data.flashcards);}catch{setError("Failed to load flashcards");}
    finally{setLoading(false);}},[setFlashcards]);

  useEffect(()=>{fetchFlashcards();},[fetchFlashcards]);

  const handleUpdate=useCallback(async(id:string,front:string,back:string)=>{
    try{await flashcardsApi.update(id,{front,back});
      setFlashcards(p=>p.map(c=>c.id===id?{...c,front,back}:c));}
    catch{}
  },[setFlashcards]);

  const handleDelete=useCallback(async(id:string)=>{
    try{await flashcardsApi.delete(id);setFlashcards(p=>p.filter(c=>c.id!==id));}
    catch{}
  },[setFlashcards]);

  return <ProtectedLayout><TopBar title="Flashcards" />
    {loading?<div className="space-y-3 mt-8">{[1,2,3].map(i=><Skeleton key={i} className="h-16 w-full" />)}</div>
    :error?<div className="text-center py-12"><p className="text-[17px] text-apple-red mb-4">{error}</p><Button variant="secondary" onClick={fetchFlashcards}>Retry</Button></div>
    :flashcards.length===0?<EmptyState title="No flashcards yet" description="Upload a document and generate flashcards from it." />
    :<div className="space-y-6 max-w-2xl mx-auto mt-6">
      <FlashcardCard key={flashcards[currentIndex]?.id} front={flashcards[currentIndex]?.front||""} back={flashcards[currentIndex]?.back||""} difficulty={(flashcards[currentIndex]?.difficulty||"medium") as FlashcardDifficulty}
        onUpdate={(f,b)=>handleUpdate(flashcards[currentIndex].id,f,b)} onDelete={()=>handleDelete(flashcards[currentIndex].id)} />
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={()=>setCurrentIndex(p=>Math.max(0,p-1))} disabled={currentIndex===0}>Previous</Button>
        <span className="text-[15px] text-text-tertiary">{currentIndex+1} of {flashcards.length}</span>
        <Button variant="ghost" onClick={()=>setCurrentIndex(p=>Math.min(flashcards.length-1,p+1))} disabled={currentIndex>=flashcards.length-1}>Next</Button>
      </div>
    </div>}
  </ProtectedLayout>;
}
