"use client";
import { Badge } from "@/components/ui/Badge";
import type { DocumentResponse } from "@/lib/types";

const statusVariant = (s: string) => s==="READY"||s==="completed" ? "success" as const : s==="PROCESSING"||s==="processing"||s==="UPLOADED"||s==="uploaded" ? "info" as const : s==="FAILED"||s==="failed" ? "danger" as const : "default" as const;
function fmtBytes(b: number) { if (b<1024) return `${b}B`; if (b<1048576) return `${(b/1024).toFixed(0)}KB`; return `${(b/1048576).toFixed(1)}MB`; }
function timeAgo(d: string) { const n=Date.now(), t=new Date(d).getTime(), s=Math.floor((n-t)/1000); if (s<60) return "just now"; const m=Math.floor(s/60); if (m<60) return `${m}m ago`; const h=Math.floor(m/60); if (h<24) return `${h}h ago`; return `${Math.floor(h/24)}d ago`; }

export function DocumentCard({ doc, onDelete }: { doc: DocumentResponse; onDelete: (id:string)=>void }) {
  return (
    <div className="flex items-center justify-between p-4 rounded-lg bg-surface-secondary border border-surface-border hover:border-surface-border-hover transition-colors">
      <div className="flex items-center gap-4 min-w-0">
        <div className="w-10 h-10 rounded-sm bg-apple-blue/15 flex items-center justify-center flex-shrink-0"><FileIcon ext={doc.extension} /></div>
        <div className="min-w-0">
          <p className="text-[15px] font-medium text-text-primary truncate max-w-[300px]">{doc.original_filename}</p>
          <p className="text-[13px] text-text-tertiary mt-0.5">{fmtBytes(doc.file_size)} · {timeAgo(doc.created_at)}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Badge variant={statusVariant(doc.status)}>{doc.status}</Badge>
        <button onClick={()=>onDelete(doc.id)} className="text-text-tertiary hover:text-apple-red transition-colors p-1" aria-label="Delete document">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" /></svg>
        </button>
      </div>
    </div>
  );
}

function FileIcon({ ext }: { ext: string }) {
  const c: Record<string,string> = { pdf:"text-apple-red", docx:"text-apple-blue", pptx:"text-apple-orange", txt:"text-text-tertiary", png:"text-apple-green", jpg:"text-apple-green", jpeg:"text-apple-green" };
  return <svg className={`w-5 h-5 ${c[ext]||"text-text-tertiary"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>;
}
