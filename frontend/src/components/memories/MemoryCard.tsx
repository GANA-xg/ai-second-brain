"use client";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useState } from "react";
import type { MemoryResponse } from "@/lib/types";

const typeColors: Record<string,"info"|"success"|"warning"> = { FACT:"info", PREFERENCE:"success", GOAL:"warning" };

export function MemoryCard({ memory, onToggleActive, onEdit, onDelete }: { memory: MemoryResponse; onToggleActive: (id:string,a:boolean)=>void; onEdit: (id:string,c:string)=>void; onDelete: (id:string)=>void }) {
  const [editing, setEditing]=useState(false);
  const [editContent, setEditContent]=useState(memory.content);
  const handleSave=()=>{ if(editContent.trim()&&editContent!==memory.content) onEdit(memory.id,editContent.trim()); setEditing(false); };
  return (
    <div className="p-4 rounded-lg bg-surface-secondary border border-surface-border">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <Badge variant={typeColors[memory.type]||"default"}>{memory.type}</Badge>
            <span className="text-[13px] text-text-tertiary">{Math.round(memory.confidence*100)}% confidence</span>
          </div>
          {editing ? (
            <div className="space-y-2">
              <textarea className="w-full rounded-sm border border-surface-border bg-white/5 px-3 py-2 text-[15px] text-text-primary resize-none focus:outline-none focus:ring-2 focus:ring-apple-blue" value={editContent} onChange={e=>setEditContent(e.target.value)} rows={3} autoFocus />
              <div className="flex gap-2"><Button size="sm" onClick={handleSave}>Save</Button><Button size="sm" variant="ghost" onClick={()=>setEditing(false)}>Cancel</Button></div>
            </div>
          ) : <p className="text-[15px] text-text-primary cursor-pointer hover:text-apple-blue-on-dark" onClick={()=>setEditing(true)}>{memory.content}</p>}
          <p className="text-[13px] text-text-tertiary mt-1.5">{new Date(memory.created_at).toLocaleDateString()}</p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={()=>onToggleActive(memory.id,!memory.is_active)} className={`w-8 h-5 rounded-pill transition-colors relative ${memory.is_active?"bg-apple-blue":"bg-white/20"}`} aria-label={memory.is_active?"Deactivate":"Activate"}>
            <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform ${memory.is_active?"translate-x-4":"translate-x-0.5"}`} />
          </button>
          <button onClick={()=>onDelete(memory.id)} className="text-text-tertiary hover:text-apple-red transition-colors p-1" aria-label="Delete memory">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
          </button>
        </div>
      </div>
    </div>
  );
}
