"use client";
import React from "react";
import ReactMarkdown from "react-markdown";
import type { Citation, MessageResponse } from "@/lib/types";
import { clsx } from "clsx";

function parseCitations(raw: Record<string,unknown>[]|null|undefined): Citation[] {
  if(!raw) return [];
  return raw.map(c=>({ document_id:String(c.document_id??""), filename:String(c.filename??"Unknown"), chunk_id:String(c.chunk_id??""), page:c.page!=null?Number(c.page):null, score:Number(c.score??0) }));
}

function CitationLink({ citation, idx }: { citation: Citation; idx: number }) {
  return <a href={`/documents/${citation.document_id}`} target="_blank" rel="noopener noreferrer"
    className="inline-flex items-center gap-1 px-[10px] py-1 rounded-pill text-[13px] font-medium bg-apple-blue/15 text-apple-blue-on-dark hover:bg-apple-blue/25 transition-colors no-underline">
    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" /></svg>
    <span>{citation.filename}{citation.page!=null?` p.${citation.page}`:""}</span>
    {idx===0&&<span className="ml-0.5 opacity-60">(source)</span>}
  </a>;
}

function UserIcon() { return <div className="flex-shrink-0 w-8 h-8 rounded-pill bg-apple-blue flex items-center justify-center text-white text-[13px] font-semibold">U</div>; }

function AssistantIcon() { return <div className="flex-shrink-0 w-8 h-8 rounded-pill bg-white/10 flex items-center justify-center text-text-secondary text-[13px] font-semibold">
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
</div>; }

function MarkdownContent({ content }: { content: string }) {
  return <div className="apple-prose text-text-primary leading-relaxed">
    <ReactMarkdown components={{
      a: ({href,children,...p})=><a href={href} target="_blank" rel="noopener noreferrer" className="text-apple-blue-on-dark underline underline-offset-2 hover:no-underline" {...p}>{children}</a>,
      code: ({className,children,...p})=>{const inline=!className;if(inline) return <code className="bg-white/10 px-1.5 py-0.5 rounded text-[15px] font-mono text-apple-orange" {...p}>{children}</code>;
        return <pre className="bg-white/5 p-4 rounded-lg overflow-x-auto text-[15px] my-3"><code className={className} {...p}>{children}</code></pre>;},
      ul: ({children,...p})=><ul className="list-disc pl-5 my-2 space-y-1" {...p}>{children}</ul>,
      ol: ({children,...p})=><ol className="list-decimal pl-5 my-2 space-y-1" {...p}>{children}</ol>,
      blockquote: ({children,...p})=><blockquote className="border-l-4 border-white/20 pl-4 my-3 italic text-text-secondary" {...p}>{children}</blockquote>,
      h1: ({children,...p})=><h1 className="text-[24px] font-semibold mt-5 mb-2" {...p}>{children}</h1>,
      h2: ({children,...p})=><h2 className="text-[20px] font-semibold mt-4 mb-2" {...p}>{children}</h2>,
      h3: ({children,...p})=><h3 className="text-[17px] font-semibold mt-3 mb-1" {...p}>{children}</h3>,
      p: ({children,...p})=><p className="my-2 leading-relaxed" {...p}>{children}</p>,
      table: ({children,...p})=><div className="overflow-x-auto my-3"><table className="min-w-full border-collapse text-[15px]" {...p}>{children}</table></div>,
      th: ({children,...p})=><th className="border border-white/10 bg-white/5 px-3 py-2 text-left font-medium" {...p}>{children}</th>,
      td: ({children,...p})=><td className="border border-white/10 px-3 py-2" {...p}>{children}</td>,
    }}>{content}</ReactMarkdown>
  </div>;
}

export function TypingIndicator() {
  return <div className="flex items-start gap-3 px-4 animate-fade-in">
    <AssistantIcon />
    <div className="flex items-center gap-1.5 px-4 py-3 rounded-pill bg-white/5">
      <span className="w-2 h-2 rounded-pill bg-text-tertiary animate-bounce" style={{animationDelay:"0ms"}} />
      <span className="w-2 h-2 rounded-pill bg-text-tertiary animate-bounce" style={{animationDelay:"150ms"}} />
      <span className="w-2 h-2 rounded-pill bg-text-tertiary animate-bounce" style={{animationDelay:"300ms"}} />
    </div>
  </div>;
}

interface MessageBubbleProps { message: MessageResponse; isStreaming?: boolean; }
export function MessageBubble({ message, isStreaming=false }: MessageBubbleProps) {
  const isUser=message.role==="user";
  const citations=parseCitations(message.citations);
  return (
    <div className={clsx("flex items-start gap-3 px-4 animate-fade-in", isUser?"flex-row-reverse":"flex-row")}>
      {isUser?<UserIcon/>:<AssistantIcon/>}
      <div className="flex flex-col gap-1.5">
        <div className={clsx("px-5 py-3.5 rounded-pill max-w-[72%] leading-relaxed", isUser?"bg-apple-blue text-white rounded-br-sm":"bg-white/5 text-text-primary rounded-bl-sm", isStreaming&&"border border-apple-blue/30")}>
          {isUser ? <p className="text-[17px] leading-relaxed whitespace-pre-wrap">{message.content}</p> : <MarkdownContent content={message.content} />}
        </div>
        {!isUser&&citations.length>0&&<div className="flex flex-wrap gap-1.5 mt-0.5">{citations.map((c,i)=><CitationLink key={`${c.chunk_id}-${i}`} citation={c} idx={i} />)}</div>}
        <span className={clsx("text-[13px] text-text-tertiary mt-0.5",isUser?"text-right":"text-left")}>
          {message.created_at?new Date(message.created_at).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):""}
        </span>
      </div>
    </div>
  );
}

export function OptimisticMessage({ content }: { content: string }) {
  return <div className="flex items-start gap-3 px-4 flex-row-reverse animate-slide-up">
    <UserIcon />
    <div className="px-5 py-3.5 rounded-pill max-w-[72%] bg-apple-blue text-white rounded-br-sm"><p className="text-[17px] leading-relaxed whitespace-pre-wrap">{content}</p></div>
  </div>;
}
