"use client";
import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { chatApi } from "@/lib/api-client";
import type { ConversationSummary } from "@/lib/types";

export default function ChatPage() {
  const router=useRouter();
  const [conversations, setConversations]=useState<ConversationSummary[]>([]);
  const [loading, setLoading]=useState(true);

  const fetchConversations=useCallback(async()=>{try{const res=await chatApi.listConversations(100,0);setConversations(res.conversations);}catch{}finally{setLoading(false);}},[]);
  useEffect(()=>{fetchConversations();},[fetchConversations]);

  const handleNew=useCallback(async()=>{try{const conv=await chatApi.createConversation();router.push(`/chat/${conv.id}`);}catch{}},[router]);
  const handleSelect=useCallback((id:string)=>{router.push(`/chat/${id}`);},[router]);

  return <ProtectedLayout><TopBar title="Chat" rightAction={<Button size="sm" onClick={handleNew}>New Chat</Button>} />
    {loading?<div className="space-y-3">{[1,2,3].map(i=><Skeleton key={i} className="h-16 w-full" />)}</div>
    :conversations.length===0?<EmptyState title="No conversations yet" description="Start a new chat to begin." action={<Button onClick={handleNew}>Start Chat</Button>} />
    :<div className="space-y-2">{conversations.map(c=><Card key={c.id} hover onClick={()=>handleSelect(c.id)} className="flex items-center gap-3">
      <div className="w-8 h-8 rounded-pill bg-apple-blue/15 flex items-center justify-center"><svg className="w-4 h-4 text-apple-blue-on-dark" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" /></svg></div>
      <div className="flex-1 min-w-0"><p className="text-[15px] font-medium text-text-primary truncate">{c.title||"Untitled"}</p><p className="text-[13px] text-text-tertiary">{c.message_count} messages</p></div>
    </Card>)}</div>}
  </ProtectedLayout>;
}
