// DocumentLibrary — uploaded-document knowledge base panel.
//
// - Upload control (file input) stores a docx/pdf/md/txt file as KNOWLEDGE only
//   (full markdown is persisted server-side; no requirements are written).
// - Per-document "Process / Extract requirements" action runs the explicit,
//   DRAFT-ONLY extraction: it shows mode/chunk progress and, when ready, hands
//   the merged draft to the existing pending-action Confirmation UI. Nothing is
//   written until the user confirms that preview.
// - Markdown preview uses the shared MarkdownRenderer.
import React, { useRef, useState } from 'react';
import { FileText, Loader2, Sparkles, Upload } from 'lucide-react';
import { api } from '../api/client';
import type {
  DocumentMarkdownPayload,
  UploadedDocumentPayload,
} from '../api/types';
import { parseAndRenderMarkdown } from './MarkdownRenderer';
import { handleError } from './Toast';
import type { UseDocumentsResult } from '../hooks/useDocuments';

interface DocumentLibraryProps {
  projectId: string | null;
  docs: UseDocumentsResult;
}

const formatBytes = (bytes: number): string => {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const idx = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / Math.pow(1024, idx)).toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
};

const extractionChip = (status: string): { label: string; className: string } => {
  switch (status) {
    case 'extraction_applied':
      return { label: 'extracted ✓', className: 'bg-emerald-100 text-emerald-800 border-emerald-300' };
    case 'extraction_pending':
      return { label: 'draft awaiting confirm', className: 'bg-amber-100 text-amber-800 border-amber-300' };
    default:
      return { label: 'knowledge only', className: 'bg-slate-100 text-slate-600 border-slate-200' };
  }
};
export const DocumentLibrary: React.FC<DocumentLibraryProps> = ({ projectId, docs }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewDoc, setPreviewDoc] = useState<DocumentMarkdownPayload | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const handleFilePicked = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ): Promise<void> => {
    const file = event.target.files?.[0];
    // Allow re-picking the same file later.
    event.target.value = '';
    if (!file || !projectId) return;
    await docs.handleUploadDocument(file);
  };

  const openPreview = async (doc: UploadedDocumentPayload): Promise<void> => {
    if (!projectId) return;
    setIsLoadingPreview(true);
    try {
      setPreviewDoc(await api.getDocumentMarkdown(projectId, doc.id));
    } catch (err) {
      handleError('Could not load the stored markdown preview.', err);
    } finally {
      setIsLoadingPreview(false);
    }
  };

  if (!projectId) {
    return (
      <div className="max-w-4xl mx-auto text-sm text-on-surface-variant">
        Create or select a project to upload documents into its knowledge base.
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* UPLOAD CONTROL — knowledge base only */}
      <section className="bg-white border border-outline rounded-2xl p-5 shadow-sm">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h3 className="font-bold text-sm text-on-surface">Knowledge Base Documents</h3>
            <p className="text-xs text-on-surface-variant mt-1">
              Upload .docx / .pdf / .md / .txt files. Uploading only adds source
              material — requirements are never written until you explicitly run an
              extraction and confirm its merge preview.
            </p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".docx,.pdf,.md,.txt"
            className="hidden"
            onChange={handleFilePicked}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={docs.isUploading}
            className="px-4 py-2 rounded-xl bg-primary text-on-primary hover:brightness-110 text-xs font-bold transition-all flex items-center gap-2 cursor-pointer shadow-md shadow-primary/15 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {docs.isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            <span>{docs.isUploading ? 'Uploading…' : 'Upload Document'}</span>
          </button>
        </div>
        {docs.lastDraftMessage && (
          <p className="mt-3 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2">
            {docs.lastDraftMessage}
          </p>
        )}
      </section>

      {/* DOCUMENT LIST */}
      <section className="space-y-2">
        {!docs.isLoadingDocuments && docs.documents.length === 0 && (
          <p className="text-xs text-on-surface-variant px-1">No documents uploaded yet.</p>
        )}
        {docs.isLoadingDocuments && (
          <p className="text-xs text-on-surface-variant px-1">Loading documents…</p>
        )}
        {docs.documents.map(doc => {
          const chip = extractionChip(doc.extraction_status);
          const isProcessing = docs.processingDocId === doc.id;
          return (
            <article key={doc.id} className="bg-white border border-outline rounded-2xl p-4 shadow-sm">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <button
                    onClick={() => void openPreview(doc)}
                    className="text-sm font-semibold text-on-surface hover:text-primary transition-colors truncate block max-w-full cursor-pointer text-left"
                    title="View stored markdown"
                  >
                    {doc.original_filename}
                  </button>
                  <p className="text-[10px] font-mono text-on-surface-variant mt-0.5">
                    {doc.original_format.toUpperCase()} · {formatBytes(doc.file_size_bytes)} · ~{doc.token_count} tokens · status {doc.status}
                  </p>
                </div>
                <span className={`text-[10px] px-2 py-1 rounded-full border font-bold ${chip.className}`}>
                  {chip.label}
                </span>
                <button
                  onClick={() => void docs.handleProcessDocument(doc)}
                  disabled={isProcessing || doc.status !== 'processed'}
                  className="px-3 py-1.5 rounded-xl bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed whitespace-nowrap"
                  title="Extract requirements as a DRAFT merge preview (nothing is written until you confirm)"
                >
                  {isProcessing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  <span>{isProcessing ? 'Extracting…' : 'Process / Extract Requirements'}</span>
                </button>
              </div>

              {/* Extraction progress: mode + chunk count surfaced clearly */}
              {isProcessing && docs.extractionProgress && (
                <div className="mt-3 text-[11px] text-primary bg-primary/5 border border-primary/20 rounded-xl px-3 py-2 font-mono">
                  Running extraction in <b>{docs.extractionProgress.mode}</b> mode
                  {docs.extractionProgress.chunkCount > 0 &&
                    ` · chunk ${Math.max(1, docs.extractionProgress.chunkIndex)}/${docs.extractionProgress.chunkCount}`}
                  … nothing is saved until you confirm the draft.
                </div>
              )}
              {doc.status === 'failed' && doc.message && (
                <div className="mt-3 text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-xl px-3 py-2">
                  {doc.message}
                </div>
              )}
            </article>
          );
        })}
      </section>

      {/* MARKDOWN PREVIEW — full canonical content from the knowledge store */}
      {(isLoadingPreview || previewDoc) && (
        <section className="bg-white border border-outline rounded-2xl p-5 shadow-sm">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-bold text-xs text-on-surface">
              {previewDoc?.original_filename ?? 'Loading…'} · stored markdown (~{previewDoc?.token_count ?? '…'} tokens)
            </h4>
            <button
              onClick={() => setPreviewDoc(null)}
              className="text-[11px] text-on-surface-variant hover:text-primary cursor-pointer"
            >
              Close
            </button>
          </div>
          {isLoadingPreview ? (
            <Loader2 className="w-5 h-5 animate-spin text-primary" />
          ) : (
            <div className="max-h-96 overflow-y-auto custom-scrollbar pr-2">
              {parseAndRenderMarkdown(previewDoc?.content_markdown ?? '')}
            </div>
          )}
        </section>
      )}
    </div>
  );
};