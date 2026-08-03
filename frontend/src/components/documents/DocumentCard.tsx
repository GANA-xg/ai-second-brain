"use client";
import React, { useCallback } from "react";
import { cn } from "@/lib/utils";
import type { DocumentResponse } from "@/lib/types";
import { FileText, FileImage, File, Trash2, Check } from "lucide-react";

interface DocumentCardProps {
  doc: DocumentResponse;
  onDelete?: (id: string) => void;
  selected?: boolean;
  onToggle?: (id: string, selected: boolean) => void;
}

export function DocumentCard({ doc, onDelete, selected, onToggle }: DocumentCardProps) {
  const getIcon = () => {
    if (doc.extension === ".pdf") return <FileText className="w-4 h-4" />;
    if ([".png", ".jpg", ".jpeg"].includes(doc.extension)) return <FileImage className="w-4 h-4" />;
    return <File className="w-4 h-4" />;
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleToggle = useCallback(() => {
    onToggle?.(doc.id, !selected);
  }, [doc.id, selected, onToggle]);

  return (
    <div
      className={cn(
        "group flex items-center gap-3 px-4 py-3 rounded-lg border transition-all duration-150",
        selected
          ? "bg-rausch-light border-rausch/30"
          : "bg-canvas border-border hover:border-border-strong hover:shadow-card"
      )}
    >
      {onToggle && (
        <button
          onClick={handleToggle}
          className={cn(
            "w-5 h-5 rounded flex items-center justify-center flex-shrink-0 border transition-all",
            selected
              ? "bg-rausch border-rausch text-white"
              : "border-border-strong hover:border-ink"
          )}
        >
          {selected && <Check className="w-3 h-3" />}
        </button>
      )}

      <div className={cn(
        "w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0",
        selected ? "bg-rausch/10 text-rausch" : "bg-canvas-soft text-ink-muted"
      )}>
        {getIcon()}
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-body-sm text-ink truncate font-medium">
          {doc.original_filename}
        </p>
        <p className="text-caption-sm text-ink-muted-soft">
          {formatSize(doc.file_size)}
          {doc.status === "processed" && (
            <span className="ml-2 text-success">&#10003; Ready</span>
          )}
          {doc.status === "processing" && (
            <span className="ml-2 text-warning">Processing...</span>
          )}
          {doc.status === "error" && (
            <span className="ml-2 text-error">Error</span>
          )}
        </p>
      </div>

      {onDelete && (
        <button
          onClick={() => onDelete(doc.id)}
          className="w-8 h-8 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 hover:bg-rausch-light text-ink-muted hover:text-error transition-all"
          aria-label="Delete document"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
