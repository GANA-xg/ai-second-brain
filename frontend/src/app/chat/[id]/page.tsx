"use client";
import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { Spinner } from "@/components/ui/Spinner";
import { Button } from "@/components/ui/Button";
import { ChatSidebar } from "@/components/chat/ChatSidebar";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageBubble, TypingIndicator, OptimisticMessage } from "@/components/chat/MessageBubble";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { chatApi } from "@/lib/api-client";
import { useDocuments } from "@/context/DocumentContext";
import { getAccessToken } from "@/lib/api";
import type { ConversationSummary, MessageResponse, StreamEvent, Citation } from "@/lib/types";
import { clsx } from "clsx";
import { Brain, Search, Zap, Sparkles } from "lucide-react";

function parseSSELine(line: string): StreamEvent | null {
  if (!line.startsWith("data: ")) return null;
  try { return JSON.parse(line.slice(6)) as StreamEvent; } catch { return null; }
}

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
  const [waitingForToken, setWaitingForToken] = useState(false);
  const { documents } = useDocuments();

  const [selectedSourceIds, setSelectedSourceIds] = useState<Set<string>>(new Set());
  const [mobileTab, setMobileTab] = useState<"sources" | "chat">("chat");
  const [noDocsSelected, setNoDocsSelected] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const scrollRAFRef = useRef<number | null>(null);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scrollToBottom = useCallback((smooth = true) => {
    if (scrollRAFRef.current) cancelAnimationFrame(scrollRAFRef.current);
    scrollRAFRef.current = requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "end" });
      scrollRAFRef.current = null;
    });
  }, []);

  const debouncedScroll = useCallback(() => {
    if (scrollTimeoutRef.current) clearTimeout(scrollTimeoutRef.current);
    scrollTimeoutRef.current = setTimeout(() => scrollToBottom(true), 100);
  }, [scrollToBottom]);

  useEffect(() => { scrollToBottom(false); }, [messages, streamContent, optimisticText, scrollToBottom]);

  const fetchData = useCallback(async () => {
    try {
      const [convosRes, detailRes] = await Promise.all([
        chatApi.listConversations(100, 0),
        chatApi.getConversation(conversationId, 1, 200),
      ]);
      setConversations(convosRes.conversations);
      setMessages(detailRes.messages);
    } catch (err) {
      console.error("[ChatPage] fetchData:", err);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    setLoading(true); setMessages([]); setStreamContent(""); setStreamCitations([]);
    setOptimisticText(null); setSending(false); setStreamError(null);
    fetchData();
  }, [fetchData]);

  const streamContentRef = useRef(streamContent);
  const streamCitationsRef = useRef(streamCitations);
  useEffect(() => { streamContentRef.current = streamContent; }, [streamContent]);
  useEffect(() => { streamCitationsRef.current = streamCitations; }, [streamCitations]);

  const sendMessageFixed = useCallback(async (question: string) => {
    if (sending) return;
    if (documents.length > 0 && selectedSourceIds.size === 0) {
      setNoDocsSelected(true);
      setStreamError("Please select at least one document source before asking a question.");
      return;
    }
    setNoDocsSelected(false);
    setOptimisticText(question); setSending(true); setStreamError(null); setStreamContent(""); setStreamCitations([]); setWaitingForToken(true);
    const controller = new AbortController();
    setAbortController(controller);
    try {
      const streamUrl = chatApi.streamUrl();
      const token = getAccessToken();
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const docIds = selectedSourceIds.size > 0 ? Array.from(selectedSourceIds) : undefined;
      const response = await fetch(streamUrl, { method: "POST", headers, body: JSON.stringify({ question, conversation_id: conversationId, document_ids: docIds }), signal: controller.signal });
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
            case "token": setWaitingForToken(false); setStreamContent((prev) => prev + (event.content ?? "")); debouncedScroll(); break;
            case "citation": setWaitingForToken(false); if (event.citations) setStreamCitations(event.citations); break;
            case "done": {
              const finalContent = streamContentRef.current;
              const finalCitations = streamCitationsRef.current;
              setMessages((prev) => {
                const hasOptimistic = prev.some((m) => m.id === "optimistic-user");
                const userMsg: MessageResponse = { id: "optimistic-user", role: "user", content: question, status: "completed", citations: null, prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() };
                return [...(hasOptimistic ? prev : [...prev, userMsg]), { id: event.message_id ?? `msg-${Date.now()}`, role: "assistant", content: finalContent, status: "completed", citations: finalCitations.map((c) => ({ ...c })), prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() }].filter((m) => m.id !== "optimistic-user");
              });
              setOptimisticText(null); setSending(false); setStreamContent(""); setStreamCitations([]); setAbortController(null); setWaitingForToken(false);
              chatApi.listConversations(100, 0).then((res) => setConversations(res.conversations)).catch((err) => console.error("[ChatPage] refresh after done:", err));
              break;
            }
            case "error": setStreamError(event.detail ?? "An error occurred"); setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); setWaitingForToken(false); break;
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") { setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); setWaitingForToken(false); return; }
      setStreamError(err instanceof Error ? err.message : "Failed to send message");
      setSending(false); setOptimisticText(null); setStreamContent(""); setStreamCitations([]); setAbortController(null); setWaitingForToken(false);
    }
  }, [conversationId, sending, debouncedScroll, selectedSourceIds, documents]);

  const handleNewConversation = useCallback(async () => { try { const conv = await chatApi.createConversation(); router.push(`/chat/${conv.id}`); } catch (err) { console.error("[ChatPage] newConv:", err); } }, [router]);
  const handleSelectConversation = useCallback((id: string) => { if (id !== conversationId) router.push(`/chat/${id}`); }, [router, conversationId]);
  const handleRefresh = useCallback(async () => { try { const res = await chatApi.listConversations(100, 0); setConversations(res.conversations); } catch (err) { console.error("[ChatPage] refresh:", err); } }, []);
  const handleRetry = useCallback(() => { if (streamError && optimisticText) sendMessageFixed(optimisticText); }, [streamError, optimisticText, sendMessageFixed]);
  const handleToggleSource = useCallback((id: string, sel: boolean) => {
    setSelectedSourceIds(prev => { const next = new Set(prev); sel ? next.add(id) : next.delete(id); return next; });
  }, []);

  if (loading) return (
    <ProtectedLayout>
      <div className="flex items-center justify-center min-h-[60vh]">
        <Spinner size="lg" />
      </div>
    </ProtectedLayout>
  );

  const streamMessage: MessageResponse | null = sending && streamContent
    ? { id: "streaming", role: "assistant", content: streamContent, status: "streaming", citations: streamCitations.length > 0 ? streamCitations.map((c) => ({ ...c })) : null, prompt_tokens: null, completion_tokens: null, total_tokens: null, error_metadata: null, created_at: new Date().toISOString() }
    : null;

  return (
    <ProtectedLayout>
      {/* Mobile tab bar */}
      <div className="fixed bottom-0 left-0 right-0 z-50 lg:hidden bg-canvas border-t border-border flex">
        {(["sources", "chat"] as const).map(tab => (
          <button key={tab} onClick={() => setMobileTab(tab)}
            className={clsx(
              "flex-1 py-3 text-caption-sm font-medium uppercase tracking-wider transition-colors",
              mobileTab === tab ? "text-rausch border-t-2 border-rausch" : "text-ink-muted"
            )}>
            {tab === "sources" ? "Sources" : "Chat"}
          </button>
        ))}
      </div>

      <div className="-mx-8 -mt-8 flex h-[calc(100vh-0rem)] max-lg:pb-12">
        {/* Sources pane */}
        <aside className={clsx(
          "w-72 flex-shrink-0 border-r border-border bg-canvas-soft flex flex-col h-full overflow-hidden",
          "max-lg:fixed max-lg:inset-0 max-lg:z-40 max-lg:w-full max-lg:pt-4",
          mobileTab === "sources" ? "max-lg:flex" : "max-lg:hidden lg:flex"
        )}>
          <div className="flex items-center justify-between px-4 pb-3">
            <h2 className="text-caption text-ink-muted uppercase tracking-wider">Sources</h2>
            <span className="text-caption-sm text-ink-muted-soft">{selectedSourceIds.size} selected</span>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-1.5">
            {documents.length === 0 && (
              <div className="text-center py-12 px-4">
                <Search className="w-8 h-8 text-ink-muted-soft mx-auto mb-3" />
                <p className="text-body-sm text-ink-muted">No documents yet</p>
                <p className="text-caption-sm text-ink-muted-soft mt-1">Upload from the dashboard</p>
              </div>
            )}
            {documents.map(doc => (
              <DocumentCard key={doc.id} doc={doc} onDelete={() => { }}
                selected={selectedSourceIds.has(doc.id)}
                onToggle={handleToggleSource} />
            ))}
          </div>
        </aside>

        {/* Chat pane */}
        <div className={clsx(
          "flex-1 flex min-w-0",
          "max-lg:flex-col",
          mobileTab === "chat" ? "max-lg:flex" : "max-lg:hidden"
        )}>
          <ChatSidebar conversations={conversations} activeConversationId={conversationId} isLoading={loading}
            onNewConversation={handleNewConversation} onSelectConversation={handleSelectConversation} onRefresh={handleRefresh} />
          <div className="flex-1 flex flex-col relative bg-canvas min-w-0">
            {/* Messages */}
            <div ref={messagesContainerRef} className="flex-1 overflow-y-auto py-6 space-y-4">
              {messages.length === 0 && !sending && !streamError && (
                <div className="flex flex-col items-center justify-center h-full text-center px-8">
                  <div className="w-16 h-16 rounded-2xl bg-rausch-light flex items-center justify-center mb-5">
                    <Brain className="w-8 h-8 text-rausch" />
                  </div>
                  <h2 className="text-display-sm text-ink mb-2">How can I help you?</h2>
                  <p className="text-body-md text-ink-muted max-w-sm mb-6">
                    Ask questions about your documents and I&apos;ll find relevant information from your knowledge base.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2 max-w-md">
                    {[
                      { icon: Search, text: "Summarize my documents" },
                      { icon: Sparkles, text: "What are the key insights?" },
                      { icon: Zap, text: "Find connections between topics" },
                    ].map((suggestion, i) => (
                      <button
                        key={i}
                        onClick={() => sendMessageFixed(suggestion.text)}
                        className="flex items-center gap-2 px-4 py-2.5 rounded-full border border-border hover:border-ink hover:shadow-card text-body-sm text-ink-muted hover:text-ink transition-all duration-200"
                      >
                        <suggestion.icon className="w-4 h-4" />
                        {suggestion.text}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)}
              {optimisticText && <OptimisticMessage content={optimisticText} />}
              {streamMessage && <MessageBubble message={streamMessage} isStreaming />
              }
              {(waitingForToken || (sending && !streamContent)) && <TypingIndicator />}
              {streamError && (
                <div className="flex flex-col items-center gap-3 px-4 py-6 animate-fade-in">
                  <div className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-rausch-light border border-rausch/20">
                    <svg className="w-4 h-4 text-error flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                    </svg>
                    <span className="text-body-sm text-error">{streamError}</span>
                  </div>
                  <Button variant="secondary" size="sm" onClick={handleRetry}>Try again</Button>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <ChatInput onSend={sendMessageFixed} disabled={sending} />
          </div>
        </div>
      </div>
    </ProtectedLayout>
  );
}
