"use client";
import React, { useCallback, useRef, useState } from "react";
import { clsx } from "clsx";

interface UploadZoneProps { onUpload: (file: File)=>void; uploading?: boolean; progress?: number; }

export function UploadZone({ onUpload, uploading, progress }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const handleDrop = useCallback((e: React.DragEvent)=>{ e.preventDefault(); setDragging(false); const f=e.dataTransfer.files[0]; if (f) onUpload(f); },[onUpload]);
  return (
    <div onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={handleDrop} onClick={()=>inputRef.current?.click()}
      className={clsx("relative border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-all duration-200",
        dragging ? "border-apple-blue bg-apple-blue/10" : "border-surface-border hover:border-surface-border-hover",
        uploading && "pointer-events-none")}>
      <input ref={inputRef} type="file" accept=".pdf,.docx,.pptx,.txt,.png,.jpg,.jpeg" className="hidden" onChange={e=>{const f=e.target.files?.[0];if(f)onUpload(f);}} disabled={uploading} />
      {uploading ? (
        <div className="space-y-3">
          <p className="text-[15px] text-text-secondary">Uploading...</p>
          {progress !== undefined && <div className="w-full max-w-xs mx-auto h-[6px] bg-white/10 rounded-pill overflow-hidden"><div className="h-full bg-apple-blue rounded-pill transition-all duration-300" style={{width:`${progress}%`}} /></div>}
        </div>
      ) : (
        <>
          <div className="mb-3 text-text-tertiary"><svg className="w-8 h-8 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" /></svg></div>
          <p className="text-[15px] text-text-secondary"><span className="font-medium text-apple-blue-on-dark">Click to upload</span> or drag and drop</p>
          <p className="text-[13px] text-text-tertiary mt-1">PDF, DOCX, PPTX, TXT, PNG, JPG (max 50MB)</p>
        </>
      )}
    </div>
  );
}
