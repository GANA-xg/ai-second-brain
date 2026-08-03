"use client";
import React from "react";
import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import type { MessageResponse, Citation } from "@/lib/types";

interface MessageBubbleProps {
  message: MessageResponse;
  isStreaming?: boolean;
  onCitationClick?: (citation: Citation) => void;
}

export function MessageBubble({ message, isStreaming, onCitationClick }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex w-full px-4 animate-fade-in-up",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      <div
        className={cn(
          "max-w-[720px] rounded-2xl px-4 py-3",
          isUser
            ? "bg-user-bubble text-white rounded-br-md"
            : "bg-canvas-soft text-ink border border-border rounded-bl-md"
        )}
      >
        {isUser ? (
          <p className="text-body-md whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose-airbnb text-body-md">
            <ReactMarkdown
              components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-5 mb-2">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-5 mb-2">{children}</ol>,
                li: ({ children }) => <li className="mb-1">{children}</li>,
                code: ({ children, className }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code className="bg-canvas-strong px-1.5 py-0.5 rounded text-rausch text-[0.9em] font-mono">
                      {children}
                    </code>
                  ) : (
                    <code className={className}>{children}</code>
                  );
                },
                pre: ({ children }) => (
                  <pre className="bg-canvas-soft border border-border rounded-xl p-4 overflow-x-auto mb-2">
                    {children}
                  </pre>
                ),
                strong: ({ children }) => (
                  <strong className="font-semibold text-ink">{children}</strong>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-rausch ml-0.5 animate-pulse-soft rounded-sm" />
            )}
          </div>
        )}

        {/* Citations */}
        {message.citations && message.citations.length > 0 && !isUser && (
          <div className="mt-3 pt-3 border-t border-border">
            <p className="text-caption-sm text-ink-muted-soft mb-2">Sources</p>
            <div className="flex flex-wrap gap-1.5">
              {message.citations.map((c, i) => {
                const cit = c as unknown as Citation;
                return (
                  <button
                    key={i}
                    onClick={() => onCitationClick?.(cit)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-canvas border border-border text-caption-sm text-ink-muted hover:border-ink hover:text-ink transition-colors"
                  >
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                    </svg>
                    {cit.filename}
                    {cit.page && <span className="text-ink-muted-soft">p{cit.page}</span>}
                    <span className="text-rausch font-medium">{Math.round(cit.score * 100)}%</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="flex w-full px-4 animate-fade-in">
      <div className="bg-canvas-soft border border-border rounded-2xl rounded-bl-md px-4 py-3">
        <div className="flex gap-1.5">
          <div className="w-2 h-2 rounded-full bg-ink-muted-soft animate-bounce" style={{ animationDelay: "0ms" }} />
          <div className="w-2 h-2 rounded-full bg-ink-muted-soft animate-bounce" style={{ animationDelay: "150ms" }} />
          <div className="w-2 h-2 rounded-full bg-ink-muted-soft animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>
    </div>
  );
}

export function OptimisticMessage({ content }: { content: string }) {
  return (
    <div className="flex w-full px-4 justify-end animate-fade-in-up">
      <div className="max-w-[720px] bg-user-bubble text-white rounded-2xl rounded-br-md px-4 py-3">
        <p className="text-body-md whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
