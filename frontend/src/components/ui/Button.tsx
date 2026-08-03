"use client";
import React from "react";
import { cn } from "@/lib/utils";
import { Spinner } from "./Spinner";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "link";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  const baseStyles =
    "btn-base inline-flex items-center justify-center gap-2 font-medium rounded-sm transition-all duration-200 select-none";

  const variants = {
    primary:
      "bg-rausch text-white hover:bg-rausch-active active:bg-rausch-active disabled:bg-rausch-disabled disabled:text-white",
    secondary:
      "bg-canvas text-ink border border-border hover:border-ink-strong active:bg-canvas-soft dark:bg-canvas-strong dark:border-border",
    ghost:
      "bg-transparent text-ink hover:bg-canvas-soft active:bg-canvas-strong",
    danger:
      "bg-error text-white hover:bg-error-hover active:bg-error-hover",
    link:
      "bg-transparent text-ink underline hover:no-underline p-0 h-auto",
  };

  const sizes = {
    sm: "h-[36px] px-4 text-button-sm",
    md: "h-[48px] px-6 text-button-md",
    lg: "h-[52px] px-8 text-button-md",
  };

  return (
    <button
      className={cn(
        baseStyles,
        variants[variant],
        variant !== "link" && sizes[size],
        loading && "pointer-events-none",
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <Spinner size="sm" className="text-current" />
      ) : icon ? (
        <span className="flex-shrink-0">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
