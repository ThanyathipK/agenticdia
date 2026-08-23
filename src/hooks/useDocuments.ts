// useDocuments — uploaded-document (knowledge base) state + handlers.
//
// Uploading a document ONLY adds source material to the project's knowledge
// store. Extraction ("process") is an explicit action that produces a DRAFT
// pending merge; the draft pending_action is pushed into the shared
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
}

export interface UseDocumentsResult {
  documents: UploadedDocumentPayload[];
  isLoadingDocuments: boolean;
  isUploading: boolean;
  processingDocId: string | null;
  extractionProgress: DocumentExtractionProgress | null;
  lastDraftMessage: string | null;
  handleUploadDocument: (file: File) => Promise<void>;
  handleProcessDocument: (doc: UploadedDocumentPayload) => Promise<void>;
  refreshDocuments: () => Promise<void>;
}

export function useDocuments(deps: DocumentsDeps): UseDocumentsResult {
  const [documents, setDocuments] = useState<UploadedDocumentPayload[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [processingDocId, setProcessingDocId] = useState<string | null>(null);
  const [extractionProgress, setExtractionProgress] = useState<DocumentExtractionProgress | null>(null);
  const [lastDraftMessage, setLastDraftMessage] = useState<string | null>(null);
  const prevPendingCount = useRef<number>(0);

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

  // When a draft is resolved (confirm or cancel removes it from the shared
  // pendingActions), refresh so extraction_status chips stay truthful.
  useEffect(() => {
    const before = prevPendingCount.current;
    prevPendingCount.current = deps.pendingActions.length;
    if (deps.pendingActions.length < before) {
      void refreshDocuments();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deps.pendingActions.length]);

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

  return {
    documents,
    isLoadingDocuments,
    isUploading,
    processingDocId,
    extractionProgress,
    lastDraftMessage,
    handleUploadDocument,
    handleProcessDocument,
    refreshDocuments,
  };
}