"use client";
import React from "react";
import { cn } from "@/lib/utils";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export function Input({ label, error, className, id, ...props }: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-caption text-ink-muted mb-1.5"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={cn(
          "input-airbnb",
          error && "border-error focus:border-error focus:shadow-none",
          className
        )}
        {...props}
      />
      {error && (
        <p className="mt-1.5 text-caption-sm text-error">{error}</p>
      )}
    </div>
  );
}
