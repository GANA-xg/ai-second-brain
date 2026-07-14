"use client";
import { clsx } from "clsx";
interface SkeletonProps { className?: string; as?: "div"|"span"|"p"; }
export function Skeleton({ className, as: Tag="div" }: SkeletonProps) {
  return <Tag className={clsx("skeleton-pulse", className)} />;
}
