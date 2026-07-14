"use client";
import React from "react";
import { clsx } from "clsx";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> { label?: string; error?: string; }

export function Input({ label, error, className, id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g,"-");
  return (
    <div className="space-y-1.5">
      {label && <label htmlFor={inputId} className="block text-[14px] font-medium text-text-secondary">{label}</label>}
      <input id={inputId}
        className={clsx("block w-full rounded-md border bg-white/5 px-4 py-[11px] text-[17px] placeholder:text-text-tertiary text-text-primary transition-all duration-150",
          "focus:outline-none focus:ring-2 focus:ring-apple-blue focus:border-apple-blue",
          error ? "border-apple-red/50" : "border-surface-border hover:border-surface-border-hover", className)}
        {...props} />
      {error && <p className="text-[14px] text-apple-red mt-1">{error}</p>}
    </div>
  );
}
