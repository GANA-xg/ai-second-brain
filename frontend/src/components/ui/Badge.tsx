"use client";
import { clsx } from "clsx";

type Variant = "default" | "success" | "warning" | "danger" | "info";

interface BadgeProps { children: React.ReactNode; variant?: Variant; className?: string; }

const variants: Record<Variant, string> = {
  default: "bg-white/10 text-text-secondary border border-white/10",
  success: "bg-apple-green/15 text-apple-green border border-apple-green/20",
  warning: "bg-apple-yellow/15 text-apple-yellow border border-apple-yellow/20",
  danger: "bg-apple-red/15 text-apple-red border border-apple-red/20",
  info: "bg-apple-blue/15 text-apple-blue-on-dark border border-apple-blue/20",
};

export function Badge({ children, variant="default", className }: BadgeProps) {
  return <span className={clsx("inline-flex items-center px-[10px] py-[2px] rounded-pill text-[13px] font-medium", variants[variant], className)}>{children}</span>;
}
