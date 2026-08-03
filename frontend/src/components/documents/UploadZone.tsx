"use client";
import React, { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { Upload, X } from "lucide-react";

interface UploadZoneProps {
  onUpload: (file: File) => void;
  uploading?: boolean;
  progress?: number;
}

export function UploadZone({ onUpload, uploading, progress }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    else if (e.type === "dragleave") setDragActive(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setDragActive(false);
      if (e.dataTransfer.files?.[0]) {
        onUpload(e.dataTransfer.files[0]);
      }
    },
    [onUpload]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.[0]) {
        onUpload(e.target.files[0]);
        e.target.value = "";
      }
    },
    [onUpload]
  );

  return (
    <div
      className={cn(
        "relative border-2 border-dashed rounded-xl transition-all duration-200 cursor-pointer",
        dragActive
          ? "border-rausch bg-rausch-light"
          : "border-border hover:border-border-strong hover:bg-canvas-soft",
        uploading && "pointer-events-none"
      )}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept=".pdf,.docx,.pptx,.txt,.png,.jpg,.jpeg"
        onChange={handleChange}
      />

      <div className="flex flex-col items-center justify-center py-10 px-6">
        {uploading ? (
          <>
            <div className="w-12 h-12 rounded-full bg-rausch-light flex items-center justify-center mb-4">
              <Upload className="w-5 h-5 text-rausch animate-bounce" />
            </div>
            <p className="text-body-sm text-ink font-medium mb-2">Uploading...</p>
            <div className="w-48 h-1.5 bg-canvas-strong rounded-full overflow-hidden">
              <div
                className="h-full bg-rausch rounded-full transition-all duration-300"
                style={{ width: `${progress || 0}%` }}
              />
            </div>
            <p className="text-caption-sm text-ink-muted-soft mt-1">{progress || 0}%</p>
          </>
        ) : (
          <>
            <div className="w-12 h-12 rounded-full bg-canvas-soft flex items-center justify-center mb-4 text-ink-muted">
              <Upload className="w-5 h-5" />
            </div>
            <p className="text-body-sm text-ink font-medium mb-1">
              Drop a file here or <span className="text-rausch">browse</span>
            </p>
            <p className="text-caption-sm text-ink-muted-soft">
              PDF, DOCX, PPTX, TXT, PNG, JPG up to 50MB
            </p>
          </>
        )}
      </div>
    </div>
  );
}
