"use client";
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageBubble, TypingIndicator, OptimisticMessage } from "@/components/chat/MessageBubble";
import { chatApi } from "@/lib/api-client";
import api, { getAccessToken } from "@/lib/api";
import type { ConversationSummary, MessageResponse, StreamEvent, Citation } from "@/lib/types";
import { clsx } from "clsx";

function parseSSELine(line: string): StreamEvent | null {
  if (!line.startsWith("data: ")) return null;
  try { return JSON.parse(line.slice(6)) as StreamEvent; } catch { return null; }
}

interface StreamState { content: string; citations: Citation[]; }

export default function ChatConversationPage() {
  const params = useParams();
  const router = useRouter();
  const conversationId = params.id as string;

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [optimisticText, setOptimisticText] = useState<string | null>(null);
  const [streamContent, setStreamContent] = useState<string>("");
  const [streamCitations, setStreamCitations] = useState<Citation[]>([]);
  const [abortController, setAbortController] = useState<AbortController | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "end" }), 50);
  }, []);

  useEffect(() => { scrollToBottom(false); }, [messages, streamContent, optimisticText, scrollToBottom]);

  const fetchData = useCallback(async () => {
    try {
      const [convosRes, detailRes] = await Promise.all([
        chatApi.listConversations(100, 0),
        chatApi.getConversation(conversationId, 1, 200),
      ]);
      setConversations(convosRes.conversations);
      setMessages(detailRes.messages);
    } catch { /* handled by interceptor */ }
    finally { setLoading(false); }
  }, [conversationId]);

  useEffect(() => {
    setLoading(true); setMessages([]); setStreamContent(""); setStreamCitations([]);
    setOptimisticText(null); setSending(false); setStreamError(null);
    fetchData();
  }, [fetchData]);

  /* ── SSE Stream request ── */
  const sendMessage = useCallback(async (question: string) => {
    if (sending) return;
    setOptimisticText(question); setSending(true); setStreamError(null); setStreamContent(""); setStreamCitations([]);
    const controller = new AbortController();
    setAbortController(controller);
    try {
      const streamUrl = chatApi.streamUrl();
      const token = getAccessToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const response = await fetch(streamUrl, { method: "POST", headers, body: JSON.stringify({ question, conversation_id: conversationId }), signal: controller.signal });
      if (!response.ok) { const errText = await response.text().catch(() => "Unknown error"); throw new Error(`Stream error (${response.status}): ${errText}`); }
      const reader = response.body?.getReader();
      if (!reader) throw new Error("Response has no body stream");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const event = parseSSELine(trimmed);
          if (!event) continue;
          switch (event.type) {
            case "token": setStreamContent((prev) => prev + (event.content ?? "")); scrollToBottom(true); break;
            case "citation": if (event.citations) setStreamCitations(event.citations); break;
            case "done": {
              setMessages((prev) => {
                const hasOptimistic = prev.some((m) => m.id === "optimistic-user");
                const userMsg: MessageResponse = { id: "optimistic-user", role: "user", content: question, status: "completed", citations: null, prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() };
                return [...(hasOptimistic ? prev : [...prev, userMsg]), { id: event.message_id ?? `msg-${Date.now()}`, role: "assistant", content: streamContent, status: "completed", citations: streamCitations.map((c) => ({ ...c })), prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() }].filter((m) => m.id !== "optimistic-user");
              });
              setOptimisticText(null); setSending(false); setStreamContent(""); setStreamCitations([]); setAbortController(null);
              chatApi.listConversations(100, 0).then((res) => setConversations(res.conversations)).catch(() => {});
              break;
            }
            case "error": setStreamError(event.detail ?? "An error occurred"); setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); break;
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") { setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); return; }
      setStreamError(err instanceof Error ? err.message : "Failed to send message");
      setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null);
    }
  }, [conversationId, sending, scrollToBottom]);

  /* Fix stale closures in done event */
  const streamContentRef = useRef(streamContent);
  const streamCitationsRef = useRef(streamCitations);
  useEffect(() => { streamContentRef.current = streamContent; }, [streamContent]);
  useEffect(() => { streamCitationsRef.current = streamCitations; }, [streamCitations]);

  const sendMessageFixed = useCallback(async (question: string) => {
    if (sending) return;
    setOptimisticText(question); setSending(true); setStreamError(null); setStreamContent(""); setStreamCitations([]);
    const controller = new AbortController();
    setAbortController(controller);
    try {
      const streamUrl = chatApi.streamUrl();
      const token = getAccessToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const response = await fetch(streamUrl, { method: "POST", headers, body: JSON.stringify({ question, conversation_id: conversationId }), signal: controller.signal });
      if (!response.ok) { const errText = await response.text().catch(() => "Unknown error"); throw new Error(`Stream error (${response.status}): ${errText}`); }
      const reader = response.body?.getReader();
      if (!reader) throw new Error("Response has no body stream");
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const event = parseSSELine(trimmed);
          if (!event) continue;
          switch (event.type) {
            case "token": setStreamContent((prev) => prev + (event.content ?? "")); scrollToBottom(true); break;
            case "citation": if (event.citations) setStreamCitations(event.citations); break;
            case "done": {
              const finalContent = streamContentRef.current;
              const finalCitations = streamCitationsRef.current;
              setMessages((prev) => {
                const hasOptimistic = prev.some((m) => m.id === "optimistic-user");
                const userMsg: MessageResponse = { id: "optimistic-user", role: "user", content: question, status: "completed", citations: null, prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() };
                return [...(hasOptimistic ? prev : [...prev, userMsg]), { id: event.message_id ?? `msg-${Date.now()}`, role: "assistant", content: finalContent, status: "completed", citations: finalCitations.map((c) => ({ ...c })), prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() }].filter((m) => m.id !== "optimistic-user");
              });
              setOptimisticText(null); setSending(false); setStreamContent(""); setStreamCitations([]); setAbortController(null);
              chatApi.listConversations(100, 0).then((res) => setConversations(res.conversations)).catch(() => {});
              break;
            }
            case "error": setStreamError(event.detail ?? "An error occurred"); setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); break;
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") { setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); return; }
      setStreamError(err instanceof Error ? err.message : "Failed to send message");
      setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null);
    }
  }, [conversationId, sending, scrollToBottom]);

  const handleNewConversation = useCallback(async () => { try { const conv = await chatApi.createConversation(); router.push(`/chat/${conv.id}`); } catch {} }, [router]);
  const handleSelectConversation = useCallback((id: string) => { if (id !== conversationId) router.push(`/chat/${id}`); }, [router, conversationId]);
  const handleRefresh = useCallback(async () => { try { const res = await chatApi.listConversations(100, 0); setConversations(res.conversations); } catch {} }, []);
  const handleRetry = useCallback(() => { if (streamError && optimisticText) sendMessageFixed(optimisticText); }, [streamError, optimisticText, sendMessageFixed]);

  if (loading) return <ProtectedLayout><div className="flex items-center justify-center min-h-[60vh]"><Spinner size="lg" /></div></ProtectedLayout>;

  const streamMessage: MessageResponse | null = sending && streamContent
    ? { id: "streaming", role: "assistant", content: streamContent, status: "streaming", citations: streamCitations.length > 0 ? streamCitations.map((c) => ({ ...c })) : null, prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() }
    : null;

  return (
    <ProtectedLayout>
      <div className="-mx-6 -mt-8 flex h-[calc(100vh-4rem)]">
        <ChatSidebar conversations={conversations} activeConversationId={conversationId} isLoading={loading}
          onNewConversation={handleNewConversation} onSelectConversation={handleSelectConversation} onRefresh={handleRefresh} />
        <div className="flex-1 flex flex-col relative bg-surface">
          <div className="absolute inset-0 pointer-events-none">
            <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-apple-blue/3 rounded-full blur-[120px]" />
          </div>
          <div ref={messagesContainerRef} className="flex-1 overflow-y-auto py-6 space-y-4">
            {messages.length === 0 && !sending && !streamError && (
              <div className="flex flex-col items-center justify-center h-full text-center px-8">
                <div className="w-16 h-16 rounded-lg bg-apple-blue/15 flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 text-apple-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
                </div>
                <h2 className="text-[24px] font-semibold text-text-primary mb-2">How can I help you?</h2>
                <p className="text-text-secondary max-w-sm text-[17px]">Ask questions about your documents and I&apos;ll find relevant information from your knowledge base.</p>
              </div>
            )}
            {messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)}
            {optimisticText && <OptimisticMessage content={optimisticText} />}
            {streamMessage && <MessageBubble message={streamMessage} isStreaming />}
            {sending && !streamContent && <TypingIndicator />}
            {streamError && (
              <div className="flex flex-col items-center gap-3 px-4 py-6">
                <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-apple-red/10 border border-apple-red/20">
                  <svg className="w-4 h-4 text-apple-red flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" /></svg>
                  <span className="text-[15px] text-apple-red">{streamError}</span>
                </div>
                <Button variant="secondary" size="sm" onClick={handleRetry}><svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" /></svg>Retry</Button>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <ChatInput onSend={sendMessageFixed} disabled={sending} />
        </div>
      </div>
    </ProtectedLayout>
  );
}
