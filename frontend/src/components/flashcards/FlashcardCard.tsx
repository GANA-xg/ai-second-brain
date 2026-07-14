"use client";
import React, { useState, useRef, useEffect, useCallback } from "react";
import { clsx } from "clsx";
import { Badge } from "@/components/ui/Badge";
import type { FlashcardDifficulty } from "@/lib/types";

const diffVariant: Record<FlashcardDifficulty,"success"|"warning"|"danger"> = { easy:"success", medium:"warning", hard:"danger" };

export function FlashcardCard({ front, back, difficulty, flipped:cf, onFlip, onUpdate, onDelete }:
  { front: string; back: string; difficulty: FlashcardDifficulty; flipped?: boolean; onFlip?: ()=>void; onUpdate?: (f:string,b:string)=>Promise<void>; onDelete?: ()=>void }) {
  const [iflip, setIflip]=useState(false);
  const [editing, setEditing]=useState<"front"|"back"|null>(null);
  const [ev, setEv]=useState("");
  const [saving, setSaving]=useState(false);
  const tr=useRef<HTMLTextAreaElement>(null);
  const flipped=cf!==undefined?cf:iflip;
  const [mounted,setMounted]=useState(false);
  useEffect(()=>setMounted(true),[]);
  useEffect(()=>{if(editing&&tr.current){tr.current.style.height="auto";tr.current.style.height=tr.current.scrollHeight+"px";tr.current.focus();}},[editing]);
  const handleFlip=useCallback(()=>{if(editing)return;if(onFlip)onFlip();else setIflip(p=>!p);},[editing,onFlip]);
  const startEdit=useCallback((s:"front"|"back")=>{setEditing(s);setEv(s==="front"?front:back);},[front,back]);
  const saveEdit=useCallback(async()=>{if(!editing||!onUpdate)return;if(!ev.trim())return;setSaving(true);try{await onUpdate(editing==="front"?ev.trim():front,editing==="back"?ev.trim():back);setEditing(null);}finally{setSaving(false);}},[editing,ev,front,back,onUpdate]);
  const cancelEdit=useCallback(()=>{setEditing(null);setEv("");},[]);

  return (
    <div className={clsx("group perspective-[1200px] w-full max-w-2xl mx-auto",!mounted&&"opacity-0")} style={{aspectRatio:"3/2"}}>
      <div onClick={handleFlip} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();handleFlip();}}} role="button" tabIndex={0}
        aria-label={flipped?"Showing answer":"Showing question"}
        className={clsx("relative w-full h-full cursor-pointer transition-transform duration-500 motion-reduce:transition-none",
          flipped?"[transform:rotateY(180deg)]":"[transform:rotateY(0deg)]","[transform-style:preserve-3d]")}>
        {/* Front */}
        <div className="absolute inset-0 rounded-lg bg-surface-secondary border border-surface-border flex flex-col [backface-visibility:hidden] p-8 md:p-10">
          <div className="flex items-center justify-between shrink-0">
            <Badge variant={diffVariant[difficulty]}>{difficulty}</Badge>
            <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
              {onUpdate&&<button onClick={e=>{e.stopPropagation();startEdit("front");}} className="p-1.5 rounded-sm text-text-tertiary hover:text-apple-blue-on-dark hover:bg-apple-blue/10 transition-colors" aria-label="Edit"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" /></svg></button>}
              {onDelete&&<button onClick={e=>{e.stopPropagation();onDelete();}} className="p-1.5 rounded-sm text-text-tertiary hover:text-apple-red hover:bg-apple-red/10 transition-colors" aria-label="Delete"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg></button>}
            </div>
          </div>
          <div className="flex-1 flex items-center justify-center">
            {editing==="front" ? (
              <div className="w-full" onClick={e=>e.stopPropagation()}>
                <textarea ref={tr} value={ev} onChange={e=>setEv(e.target.value)} onKeyDown={e=>{if(e.key==="Escape")cancelEdit();else if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();saveEdit();}}}
                  className="w-full resize-none bg-transparent text-center text-[28px] font-semibold text-text-primary leading-snug outline-none border-b-2 border-apple-blue" rows={3} aria-label="Edit question" />
                <div className="flex items-center justify-center gap-2 mt-3">
                  <button onClick={saveEdit} disabled={saving||!ev.trim()} className="text-[15px] font-medium text-apple-blue-on-dark disabled:opacity-40">{saving?"Saving…":"Save"}</button>
                  <span className="text-text-tertiary">·</span>
                  <button onClick={cancelEdit} className="text-[15px] font-medium text-text-tertiary hover:text-text-secondary">Cancel</button>
                </div>
              </div>
            ) : <p className="text-center text-[28px] font-semibold text-text-primary leading-snug select-none">{front}</p>}
          </div>
          <p className="text-center text-[13px] text-text-tertiary shrink-0 mt-2">Tap to reveal answer</p>
        </div>
        {/* Back */}
        <div className="absolute inset-0 rounded-lg bg-surface-secondary border border-surface-border flex flex-col [backface-visibility:hidden] [transform:rotateY(180deg)] p-8 md:p-10">
          <div className="flex items-center justify-between shrink-0">
            <Badge variant={diffVariant[difficulty]}>{difficulty}</Badge>
            <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
              {onUpdate&&<button onClick={e=>{e.stopPropagation();startEdit("back");}} className="p-1.5 rounded-sm text-text-tertiary hover:text-apple-blue-on-dark hover:bg-apple-blue/10 transition-colors" aria-label="Edit"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" /></svg></button>}
              {onDelete&&<button onClick={e=>{e.stopPropagation();onDelete();}} className="p-1.5 rounded-sm text-text-tertiary hover:text-apple-red hover:bg-apple-red/10 transition-colors" aria-label="Delete"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg></button>}
            </div>
          </div>
          <div className="flex-1 flex items-center justify-center">
            {editing==="back" ? (
              <div className="w-full" onClick={e=>e.stopPropagation()}>
                <textarea ref={tr} value={ev} onChange={e=>setEv(e.target.value)} onKeyDown={e=>{if(e.key==="Escape")cancelEdit();else if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();saveEdit();}}}
                  className="w-full resize-none bg-transparent text-center text-[28px] font-semibold text-text-primary leading-snug outline-none border-b-2 border-apple-blue" rows={3} aria-label="Edit answer" />
                <div className="flex items-center justify-center gap-2 mt-3">
                  <button onClick={saveEdit} disabled={saving||!ev.trim()} className="text-[15px] font-medium text-apple-blue-on-dark disabled:opacity-40">{saving?"Saving…":"Save"}</button>
                  <span className="text-text-tertiary">·</span>
                  <button onClick={cancelEdit} className="text-[15px] font-medium text-text-tertiary hover:text-text-secondary">Cancel</button>
                </div>
              </div>
            ) : <p className="text-center text-[28px] font-semibold text-text-primary leading-snug select-none">{back}</p>}
          </div>
          <p className="text-center text-[13px] text-text-tertiary shrink-0 mt-2">Tap to see question</p>
        </div>
      </div>
    </div>
  );
}
