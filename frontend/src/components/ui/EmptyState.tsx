"use client";
import React from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center py-16 px-8 text-center animate-fade-in",
        className
      )}
    >
      {icon && (
        <div className="w-16 h-16 rounded-full bg-canvas-soft flex items-center justify-center mb-6 text-ink-muted">
          {icon}
        </div>
      )}
      <h3 className="text-display-sm text-ink mb-2">{title}</h3>
      {description && (
        <p className="text-body-md text-ink-muted max-w-sm mb-6">{description}</p>
      )}
      {action && <div>{action}</div>}
    </div>
  );
}
