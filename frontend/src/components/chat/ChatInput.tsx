"use client";
import React, { useState, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [value, adjustHeight]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }, [value, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="border-t border-border bg-canvas px-4 py-3">
      <div className="relative flex items-end gap-2 bg-canvas-soft rounded-xl border border-border px-4 py-3 transition-all duration-200 focus-within:border-ink focus-within:shadow-focus-ring">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder || "Ask anything about your documents..."}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent resize-none outline-none text-body-md text-ink placeholder:text-ink-muted-soft max-h-[200px] leading-relaxed"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className={cn(
            "w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-200",
            value.trim() && !disabled
              ? "bg-rausch text-white hover:bg-rausch-active active:scale-95"
              : "bg-canvas-strong text-ink-muted-soft cursor-not-allowed"
          )}
          aria-label="Send message"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
            />
          </svg>
        </button>
      </div>
      <p className="text-center text-caption-sm text-ink-muted-soft mt-2">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  );
}
