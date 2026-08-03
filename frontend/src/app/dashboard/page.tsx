"use client";
import React, { useState, useCallback } from "react";
import { ProtectedLayout } from "@/components/layout/ProtectedLayout";
import { TopBar } from "@/components/layout/TopBar";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { DocumentCard } from "@/components/documents/DocumentCard";
import { UploadZone } from "@/components/documents/UploadZone";
import { useToast } from "@/components/ui/Toast";
import { documentsApi } from "@/lib/api-client";
import { useDocuments } from "@/context/DocumentContext";
import { FileText } from "lucide-react";

export default function DashboardPage() {
  const { documents, isLoading: loading, error, refresh } = useDocuments();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const { toast } = useToast();

  const handleUpload = useCallback(async (file: File) => {
    setUploading(true);
    setUploadProgress(0);
    try {
      const interval = setInterval(() => setUploadProgress(p => Math.min(p + 15, 85)), 200);
      await documentsApi.upload(file);
      clearInterval(interval);
      setUploadProgress(100);
      setTimeout(() => {
        setUploadProgress(0);
        setUploading(false);
        refresh();
        toast("Document uploaded successfully");
      }, 400);
    } catch (err) {
      setUploading(false);
      setUploadProgress(0);
      console.error("[Dashboard] upload:", err);
      toast("Upload failed", "error");
    }
  }, [refresh, toast]);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await documentsApi.delete(id);
      refresh();
      toast("Document deleted");
    } catch (err) {
      console.error("[Dashboard] delete:", err);
      toast("Failed to delete document", "error");
    }
  }, [refresh, toast]);

  return (
    <ProtectedLayout>
      <TopBar
        title="Documents"
        subtitle="Manage your knowledge base"
        rightAction={
          documents.length > 0 ? (
            <span className="text-body-sm text-ink-muted">
              {documents.length} document{documents.length !== 1 ? "s" : ""}
            </span>
          ) : undefined
        }
      />

      <div className="mb-8">
        <UploadZone onUpload={handleUpload} uploading={uploading} progress={uploadProgress} />
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : error ? (
        <div className="text-center py-16">
          <p className="text-body-md text-error mb-4">{error}</p>
          <Button variant="secondary" onClick={refresh}>Retry</Button>
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          title="No documents yet"
          description="Upload a PDF, DOCX, or TXT to get started with your AI knowledge base."
          icon={<FileText className="w-8 h-8" />}
        />
      ) : (
        <div className="space-y-2">
          {documents.map(doc => (
            <DocumentCard key={doc.id} doc={doc} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </ProtectedLayout>
  );
}
