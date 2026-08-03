"use client";
import React from "react";
import { cn } from "@/lib/utils";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  hover?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
}

export function Card({ hover, onClick, children, className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "airbnb-card",
        hover && "cursor-pointer hover:shadow-airbnb-hover hover:border-border-strong active:scale-[0.99] transition-all duration-200",
        onClick && "cursor-pointer",
        className
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      {...props}
    >
      {children}
    </div>
  );
}
