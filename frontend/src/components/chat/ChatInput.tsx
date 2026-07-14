"use client";

import React, { useRef, useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { clsx } from "clsx";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Ask anything...",
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [focused, setFocused] = useState(false);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [adjustHeight]);

  const handleSubmit = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    const text = el.value.trim();
    if (!text || disabled) return;
    onSend(text);
    el.value = "";
    adjustHeight();
  }, [disabled, onSend, adjustHeight]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="relative z-10 px-4 pb-6 pt-2">
      <div className="max-w-4xl mx-auto">
        {/* Animated gradient border wrapper */}
        <div
          className={clsx(
            "rounded-[34px] p-[1.5px] transition-all duration-500",
            "bg-[length:300%_300%] animate-border-glow",
            focused
              ? "bg-gradient-to-r from-glow-violet via-glow-amber to-glow-violet"
              : "bg-gradient-to-r from-glow-violet/40 via-glow-amber/30 to-glow-violet/40"
          )}
        >
          {/* Glassmorphism inner panel */}
          <div
            className={clsx(
              "rounded-[33px] backdrop-blur-xl transition-all duration-300",
              "bg-neutral-900/60 dark:bg-neutral-900/70",
              "shadow-[0_8px_40px_rgba(0,0,0,0.3),inset_0_1px_0_rgba(255,255,255,0.06)]"
            )}
          >
            {/* Textarea */}
            <div className="px-5 pt-4 pb-2">
              <textarea
                ref={textareaRef}
                onInput={adjustHeight}
                onKeyDown={handleKeyDown}
                onFocus={() => setFocused(true)}
                onBlur={() => setFocused(false)}
                disabled={disabled}
                placeholder={placeholder}
                rows={1}
                aria-label="Message input"
                className={clsx(
                  "block w-full resize-none bg-transparent",
                  "text-xl leading-relaxed text-white placeholder:text-neutral-500",
                  "font-sans tracking-tight",
                  "focus:outline-none",
                  disabled && "opacity-50 cursor-not-allowed"
                )}
                style={{ maxHeight: 192 }}
              />
            </div>

            {/* Bottom toolbar */}
            <div className="flex items-center px-3 pb-3 gap-1">
              {/* Left: Prompts pill */}
              <ToolbarButton
                icon={
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"
                    />
                  </svg>
                }
                label="Prompts"
                pill
              />

              <div className="flex-1" />

              {/* Middle: Paperclip */}
              <ToolbarButton
                icon={
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13"
                    />
                  </svg>
                }
                ariaLabel="Attach file"
              />

              {/* Right: Microphone capsule */}
              <button
                type="button"
                disabled
                aria-label="Voice input"
                className={clsx(
                  "flex items-center gap-2 px-3 py-1.5 rounded-full",
                  "text-xs font-medium text-neutral-400",
                  "bg-white/5 border border-white/10",
                  "opacity-50 cursor-not-allowed"
                )}
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
                  />
                </svg>
                <span>Mic</span>
                <span className="w-4 h-2.5 rounded-full bg-neutral-700 relative">
                  <span className="absolute inset-0.5 rounded-full bg-neutral-500" />
                </span>
              </button>

              {/* Far right: Send button */}
              <motion.button
                onClick={handleSubmit}
                disabled={disabled}
                aria-label="Send message"
                whileHover={disabled ? {} : { scale: 1.05 }}
                whileTap={disabled ? {} : { scale: 0.92 }}
                className={clsx(
                  "flex-shrink-0 flex items-center justify-center w-10 h-10 rounded-full",
                  "transition-shadow duration-200",
                  disabled
                    ? "bg-neutral-700 text-neutral-500 cursor-not-allowed"
                    : "bg-gradient-to-br from-glow-violet to-purple-600 text-white shadow-lg shadow-purple-500/20 hover:shadow-purple-500/40 active:shadow-sm"
                )}
              >
                <svg
                  className="w-5 h-5 -rotate-45"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
                  />
                </svg>
              </motion.button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Small toolbar icon button ── */

interface ToolbarButtonProps {
  icon: React.ReactNode;
  label?: string;
  pill?: boolean;
  ariaLabel?: string;
}

function ToolbarButton({ icon, label, pill, ariaLabel }: ToolbarButtonProps) {
  return (
    <div
      aria-label={ariaLabel}
      className={clsx(
        "flex items-center gap-1.5 transition-all duration-200 cursor-default",
        "text-neutral-400 hover:text-white",
        pill
          ? "px-3 py-1.5 rounded-full text-xs font-medium bg-white/5 border border-white/10 hover:bg-white/10 hover:border-white/20"
          : "p-1.5 rounded-lg hover:bg-white/5"
      )}
    >
      {icon}
      {label && <span>{label}</span>}
    </div>
  );
}
