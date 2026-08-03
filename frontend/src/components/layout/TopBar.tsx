"use client";
import React from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

interface TopBarProps {
  title: string;
  subtitle?: string;
  backHref?: string;
  rightAction?: React.ReactNode;
  tabs?: Array<{ label: string; active?: boolean; onClick?: () => void }>;
  className?: string;
}

export function TopBar({ title, subtitle, backHref, rightAction, tabs, className }: TopBarProps) {
  const router = useRouter();

  return (
    <div className={cn("mb-8", className)}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-3">
          {backHref && (
            <button
              onClick={() => router.push(backHref)}
              className="w-8 h-8 rounded-full flex items-center justify-center hover:bg-canvas-soft transition-colors text-ink-muted"
              aria-label="Go back"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}
          <div>
            <h1 className="text-display-xl text-ink">{title}</h1>
            {subtitle && (
              <p className="text-body-sm text-ink-muted mt-0.5">{subtitle}</p>
            )}
          </div>
        </div>
        {rightAction && <div>{rightAction}</div>}
      </div>

      {tabs && tabs.length > 0 && (
        <div className="flex gap-6 mt-4 border-b border-border">
          {tabs.map((tab, i) => (
            <button
              key={i}
              onClick={tab.onClick}
              className={cn(
                "pb-3 text-nav-link transition-colors relative",
                tab.active ? "text-ink" : "text-ink-muted hover:text-ink"
              )}
            >
              {tab.label}
              {tab.active && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-ink rounded-full" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
