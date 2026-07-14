"use client";
import React, { useState, useCallback, useEffect, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import { clsx } from "clsx";
import { chatApi } from "@/lib/api-client";
import type { ConversationSummary } from "@/lib/types";

function RenameInput({ initial, onSave, onCancel }: { initial: string; onSave: (t:string)=>Promise<void>; onCancel: ()=>void }) {
  const [v,setV]=useState(initial);
  const ref=useRef<HTMLInputElement>(null);
  useEffect(()=>{ref.current?.focus();ref.current?.select();},[]);
  const submit=useCallback(async()=>{const t=v.trim();if(t&&t!==initial)await onSave(t);onCancel();},[v,initial,onSave,onCancel]);
  return <input ref={ref} value={v} onChange={e=>setV(e.target.value)} onBlur={submit} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();submit();}if(e.key==="Escape")onCancel();}}
    className="w-full bg-transparent text-[15px] font-medium text-text-primary outline-none border-b border-apple-blue py-0.5" />;
}

interface ChatSidebarProps {
  conversations: ConversationSummary[]; activeConversationId?: string; isLoading?: boolean;
  onNewConversation: ()=>Promise<void>; onSelectConversation: (id:string)=>void; onRefresh: ()=>Promise<void>;
}

export function ChatSidebar({ conversations, activeConversationId, isLoading, onNewConversation, onSelectConversation, onRefresh }: ChatSidebarProps) {
  const [renamingId, setRenamingId]=useState<string|null>(null);
  const handleRename=async(id:string,title:string)=>{await chatApi.updateConversation(id,title);await onRefresh();setRenamingId(null);};
  const handleDelete=async(id:string)=>{await chatApi.deleteConversation(id);await onRefresh();};

  return (
    <aside className="w-72 flex-shrink-0 border-r border-surface-border bg-black flex flex-col h-full">
      <div className="px-4 pt-4 pb-3 flex items-center justify-between">
        <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-wider">Conversations</h2>
        <button onClick={onNewConversation} disabled={isLoading}
          className="flex items-center justify-center w-7 h-7 rounded-sm text-text-tertiary hover:text-apple-blue-on-dark hover:bg-apple-blue/10 transition-colors" aria-label="New conversation">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5">
        {conversations.length===0&&!isLoading&&<p className="text-[15px] text-text-tertiary text-center py-8 px-4">No conversations yet.<br /><span className="text-[13px]">Click + to start one.</span></p>}
        {conversations.map(conv=>{
          const isActive=conv.id===activeConversationId;
          const isRenaming=renamingId===conv.id;
          return (
            <div key={conv.id} className={clsx("group relative flex items-center gap-1 px-3 py-2 rounded-sm cursor-pointer transition-colors duration-150",
              isActive?"bg-apple-blue/15":"hover:bg-white/5")} onClick={()=>!isRenaming&&onSelectConversation(conv.id)}>
              <svg className={clsx("w-4 h-4 flex-shrink-0",isActive?"text-apple-blue-on-dark":"text-text-tertiary")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
              </svg>
              <div className="flex-1 min-w-0">
                {isRenaming ? <RenameInput initial={conv.title} onSave={t=>handleRename(conv.id,t)} onCancel={()=>setRenamingId(null)} />
                  : <span className={clsx("block text-[15px] truncate",isActive?"font-medium text-apple-blue-on-dark":"text-text-secondary")}>{conv.title||"Untitled"}</span>}
              </div>
              {!isRenaming && <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onClick={e=>{e.stopPropagation();setRenamingId(conv.id);}} className="p-1 rounded text-text-tertiary hover:text-text-secondary hover:bg-white/10" aria-label="Rename">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" /></svg>
                </button>
                <button onClick={e=>{e.stopPropagation();handleDelete(conv.id);}} className="p-1 rounded text-text-tertiary hover:text-apple-red hover:bg-apple-red/10" aria-label="Delete">
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
                </button>
              </div>}
            </div>
          );
        })}
      </nav>
      <div className="px-3 pb-3 pt-2 border-t border-surface-border">
        <button onClick={onRefresh} disabled={isLoading} className="flex items-center gap-2 w-full px-3 py-2 rounded-sm text-[13px] font-medium text-text-tertiary hover:text-text-secondary hover:bg-white/5 transition-colors">
          <svg className={clsx("w-3.5 h-3.5",isLoading&&"animate-spin")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>
          Refresh
        </button>
      </div>
    </aside>
  );
}
