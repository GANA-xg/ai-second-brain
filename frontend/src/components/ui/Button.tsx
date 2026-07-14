"use client";
import React from "react";
import { clsx } from "clsx";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant; size?: Size; loading?: boolean;
}

const variants: Record<Variant, string> = {
  primary: "bg-apple-blue text-white hover:bg-[#0055a3] active:scale-[0.97] shadow-sm",
  secondary: "bg-white/5 text-white hover:bg-white/10 active:scale-[0.97] border border-white/10",
  ghost: "text-text-secondary hover:text-text-primary hover:bg-white/5 active:scale-[0.97]",
  danger: "bg-apple-red text-white hover:bg-[#d93a2e] active:scale-[0.97]",
};

const sizes: Record<Size, string> = {
  sm: "px-[15px] py-[8px] text-[14px] rounded-pill",
  md: "px-[22px] py-[11px] text-[17px] rounded-pill",
  lg: "px-[28px] py-[14px] text-[18px] rounded-pill",
};

export function Button({ variant="primary", size="md", loading, disabled, className, children, ...props }: ButtonProps) {
  return (
    <button className={clsx("inline-flex items-center justify-center font-medium transition-all duration-150 focus-ring disabled:opacity-40 disabled:cursor-not-allowed", variants[variant], sizes[size], className)}
      disabled={disabled||loading} {...props}>
      {loading && <svg className="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>}
      {children}
    </button>
  );
}
