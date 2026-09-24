// useDocuments — uploaded-document (knowledge base) state + handlers.
//
// DOC-UPLOAD 1.x — frontend half of FLOW 14 (backend routes 2.1–2.4, repo 4.1–4.5).
// Uploading a document ONLY adds source material to the project's knowledge
// store. Extraction ("process", FLOW 15) is an explicit action that produces a
// DRAFT pending merge; the draft pending_action is pushed into the shared
// `pendingActions` state so the existing ConfirmationPanel offers Confirm /
// Cancel and NOTHING is written to requirements until the user confirms.
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api } from '../api/client';
import type {
  PendingActionPayload,
  ProcessDocumentResponse,
  UploadedDocumentPayload,
} from '../api/types';
import { handleError } from '../components/Toast';

export interface DocumentExtractionProgress {
  documentId: string;
  mode: string;
  chunkIndex: number;
  chunkCount: number;
}

export interface DocumentsDeps {
  projectId: string | null;
  pendingActions: PendingActionPayload[];
  setPendingActions: Dispatch<SetStateAction<PendingActionPayload[]>>;
  /**
   * SSE bridge supplied by the composition root: `useProjectSync` forwards
   * `document_extraction_progress` frames here so the progress readout updates
   * LIVE (chunk X/N) during long extractions instead of hanging on the
   * optimistic placeholder set when processing starts.
   */
  registerLiveProgress?: (fn: (p: DocumentExtractionProgress | null) => void) => void;
}

export interface UseDocumentsResult {
  documents: UploadedDocumentPayload[];
  isLoadingDocuments: boolean;
  isUploading: boolean;
  processingDocId: string | null;
  deletingDocId: string | null;
  extractionProgress: DocumentExtractionProgress | null;
  lastDraftMessage: string | null;
  handleUploadDocument: (file: File) => Promise<void>;
  handleProcessDocument: (doc: UploadedDocumentPayload) => Promise<void>;
  /** Permanently removes a document; resolves to true on success. */
  handleDeleteDocument: (doc: UploadedDocumentPayload) => Promise<boolean>;
  refreshDocuments: () => Promise<void>;
}

export function useDocuments(deps: DocumentsDeps): UseDocumentsResult {
  // DOC-UPLOAD 1.4 — Documents state: rows rendered by DocumentLibrary with their
  //             extraction chip (knowledge only / draft awaiting confirm / extracted).
  const [documents, setDocuments] = useState<UploadedDocumentPayload[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [processingDocId, setProcessingDocId] = useState<string | null>(null);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);
  const [extractionProgress, setExtractionProgress] = useState<DocumentExtractionProgress | null>(null);
  const [lastDraftMessage, setLastDraftMessage] = useState<string | null>(null);
  const prevPendingCount = useRef<number>(0);

  // DOC-UPLOAD 1.3 — Knowledge-base list load (DOC-UPLOAD 2.2). Runs on project switch and
  //             is the reconciliation point after upload / extraction / delete.
  const refreshDocuments = useCallback(async () => {
    if (!deps.projectId) {
      setDocuments([]);
      return;
    }
    setIsLoadingDocuments(true);
    try {
      const docs = await api.listDocuments(deps.projectId);
      setDocuments(docs);
    } catch (err) {
      handleError('Failed to load uploaded documents.', err);
    } finally {
      setIsLoadingDocuments(false);
    }
  }, [deps.projectId]);

  // Reload the knowledge list when switching projects.
  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  // SSE live-progress bridge. `useProjectState` wires a stable setter here that
  // `useProjectSync`'s SSE handler drives with document_extraction_progress
  // frames, so the DocumentLibrary's "chunk X/N" readout advances in real time
  // (the old optimist placeholder stayed at 0/N for the whole run).
  useEffect(() => {
    if (!deps.registerLiveProgress) return;
    deps.registerLiveProgress(setExtractionProgress);
    return () => deps.registerLiveProgress?.(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deps.registerLiveProgress]);

  // DOC-UPLOAD 1.8 — Draft-resolution refresh: when the pending list SHRINKS (the extraction
  //             draft was confirmed or cancelled — CONFIRM/CANCELLATION flows), re-read the
  //             documents so each row's extraction_status chip stays truthful.
  useEffect(() => {
    const before = prevPendingCount.current;
    prevPendingCount.current = deps.pendingActions.length;
    if (deps.pendingActions.length < before) {
      void refreshDocuments();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deps.pendingActions.length]);

  // DOC-UPLOAD 1.2 — Upload handler. POSTs the file (DOC-UPLOAD 2.1), then branches on the
  //             returned status: `failed` (e.g. the 2.1.5 needs-OCR record) surfaces the
  //             server message as an amber notice and the row stays visible with status
  //             'failed'; success clears the notice. Either way the list is re-read so the
  //             new row (or failed row) appears immediately.
  const handleUploadDocument = useCallback(async (file: File) => {
    if (!deps.projectId) return;
    setIsUploading(true);
    try {
      const doc = await api.uploadDocument(deps.projectId, file);
      if (doc.status === 'failed') {
        // e.g. scanned PDF -> explicit needs-OCR message, never a silent stub.
        setLastDraftMessage(doc.message || 'Upload stored with status failed.');
      } else {
        setLastDraftMessage(null);
      }
      await refreshDocuments();
    } catch (err) {
      handleError('Document upload failed.', err);
    } finally {
      setIsUploading(false);
    }
  }, [deps.projectId, refreshDocuments]);

  const handleProcessDocument = useCallback(async (doc: UploadedDocumentPayload) => {
    if (!deps.projectId || processingDocId) return;
    setProcessingDocId(doc.id);
    setLastDraftMessage(null);
    // Optimistic progress placeholder until the first chunk event lands.
    setExtractionProgress({
      documentId: doc.id,
      mode: doc.token_count <= 0 ? 'full' : 'chunked',
      chunkIndex: 0,
      chunkCount: 0,
    });
    try {
      const res: ProcessDocumentResponse = await api.processDocument(deps.projectId, doc.id);
      if (res.pending_action_id) {
        // Surface the DRAFT through the existing confirmation flow. Nothing is
        // written until the user confirms this single merged preview.
        const draft: PendingActionPayload = {
          id: res.pending_action_id,
          project_id: deps.projectId,
          action_type: 'INSERT_CHUNKED_REQUIREMENTS',
          original_user_message:
            `Extract requirements from uploaded document '${doc.original_filename}'.`,
        };
        deps.setPendingActions(prev =>
          prev.some(a => a.id === draft.id) ? prev : [...prev, draft],
        );
        setLastDraftMessage(res.message || null);
      }
    } catch (err) {
      handleError('Document extraction failed. No changes were written.', err);
    } finally {
      setProcessingDocId(null);
      setExtractionProgress(null);
      await refreshDocuments();
    }
  }, [deps, processingDocId, refreshDocuments]);

  // DOC-UPLOAD 1.6 — Remove handler (DOC-UPLOAD 2.4). The deleted document's DRAFT
  //             pending_action was already discarded server-side (2.4.2); the pending
  //             panel evicts it on the next SSE sync / project refresh — this only
  //             re-reads the knowledge list. Returns a boolean so the ConfirmModal can
  //             stay open on failure.
  const handleDeleteDocument = useCallback(async (doc: UploadedDocumentPayload) => {
    if (!deps.projectId || deletingDocId) return false;
    setDeletingDocId(doc.id);
    try {
      await api.deleteDocument(deps.projectId, doc.id);
      // The deleted doc's DRAFT pending_action was discarded server-side; the
      // next SSE sync / project refresh will evict it from the pending panel.
      await refreshDocuments();
      return true;
    } catch (err) {
      handleError('Failed to remove the document.', err);
      return false;
    } finally {
      setDeletingDocId(null);
    }
  }, [deps.projectId, deletingDocId, refreshDocuments]);

  return {
    documents,
    isLoadingDocuments,
    isUploading,
    processingDocId,
    deletingDocId,
    extractionProgress,
    lastDraftMessage,
    handleUploadDocument,
    handleProcessDocument,
    handleDeleteDocument,
    refreshDocuments,
  };
}