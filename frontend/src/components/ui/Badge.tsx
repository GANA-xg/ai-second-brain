"use client";
import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps {
  variant?: "default" | "success" | "warning" | "danger" | "info";
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = "default", children, className }: BadgeProps) {
  const variants = {
    default: "bg-canvas-strong text-ink",
    success: "bg-success-light text-success",
    warning: "bg-warning-light text-warning",
    danger: "bg-rausch-light text-rausch",
    info: "bg-info-light text-info",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-pill text-badge font-semibold",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
