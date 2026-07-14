"use client";
import React from "react";
import { clsx } from "clsx";

interface CardProps { children: React.ReactNode; className?: string; hover?: boolean; onClick?: () => void; }

export function Card({ children, className, hover, onClick }: CardProps) {
  return (
    <div className={clsx("rounded-lg bg-surface-secondary border border-surface-border p-5",
      hover && "transition-all duration-200 hover:bg-surface-card-hover hover:border-surface-border-hover cursor-pointer",
      onClick && "cursor-pointer", className)}
      onClick={onClick} role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e: React.KeyboardEvent) => { if (e.key==="Enter"||e.key===" ") { e.preventDefault(); onClick(); } } : undefined}>
      {children}
    </div>
  );
}
