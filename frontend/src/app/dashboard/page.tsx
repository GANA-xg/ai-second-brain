"use client";
import React, { useState, useCallback, useEffect } from "react";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { UploadZone } from "@/components/documents/UploadZone";
import { documentsApi } from "@/lib/api-client";
import type { DocumentResponse } from "@/lib/types";

export default function DashboardPage() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string|null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true); setError(null);
    try { const data = await documentsApi.list(); setDocuments(data.documents); }
    catch { setError("Failed to load documents"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchDocuments(); }, [fetchDocuments]);

  const handleUpload = useCallback(async (file: File) => {
    setUploading(true); setUploadProgress(0);
    try {
      const interval = setInterval(() => setUploadProgress(p => Math.min(p+15,85)), 200);
      await documentsApi.upload(file);
      clearInterval(interval);
      setUploadProgress(100);
      setTimeout(() => { setUploadProgress(0); setUploading(false); fetchDocuments(); }, 400);
    } catch { setUploading(false); setUploadProgress(0); }
  }, [fetchDocuments]);

  const handleDelete = useCallback(async (id: string) => {
    try { await documentsApi.delete(id); setDocuments(p => p.filter(d => d.id !== id)); }
    catch { /* handled by interceptor */ }
  }, []);

  return (
    <ProtectedLayout>
      <TopBar title="Documents" />

      {/* Upload Zone */}
      <div className="mb-8">
        <UploadZone onUpload={handleUpload} uploading={uploading} progress={uploadProgress} />
      </div>

      {/* Documents List */}
      {loading ? (
        <div className="space-y-3">
          {[1,2,3].map(i=><Skeleton key={i} className="h-16 w-full" />)}
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-[17px] text-apple-red mb-4">{error}</p>
          <Button variant="secondary" onClick={fetchDocuments}>Retry</Button>
        </div>
      ) : documents.length === 0 ? (
        <EmptyState title="No documents yet" description="Upload a PDF, DOCX, or TXT to get started." icon={<svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>} />
      ) : (
        <div className="space-y-3">
          {documents.map(doc => <DocumentCard key={doc.id} doc={doc} onDelete={handleDelete} />)}
        </div>
      )}
    </ProtectedLayout>
  );
}
