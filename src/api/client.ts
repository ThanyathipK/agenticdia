// ============================================================================
// Typed API client — every backend endpoint used by the app is wrapped in a
// strongly-typed function so callers never touch raw `axios` responses or cast
// payloads to `any`. Mirrors `backend/app/routes/*` and `backend/app/schemas.py`.
// ============================================================================

import axios from 'axios';
import type {
  ActionStatusResponse,
  ArtifactLockResponse,
  ConfirmActionResponse,
  DocumentMarkdownPayload,
  HealthPayload,
  PendingActionPayload,
  ProcessDocumentResponse,
  ProcessRequirementsRequest,
  ProcessRequirementsResponse,
  ProjectCreated,
  ProjectDeleteResponse,
  ProjectSummary,
  RequirementStatePayload,
  UploadedDocumentPayload,
} from './types';

async function get<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const { data } = await axios.get<T>(url, { params });
  return data;
}

async function post<T>(
  url: string,
  body?: unknown,
  params?: Record<string, unknown>,
  signal?: AbortSignal
): Promise<T> {
  const { data } = await axios.post<T>(url, body ?? null, { params, signal });
  return data;
}

async function put<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await axios.put<T>(url, body ?? {});
  return data;
}

async function del<T>(url: string): Promise<T> {
  const { data } = await axios.delete<T>(url);
  return data;
}

// Multipart upload helper — the existing helpers above are JSON-only. The
// browser supplies the multipart boundary, so Content-Type must NOT be set
// manually here.
async function postFormData<T>(url: string, formData: FormData): Promise<T> {
  const { data } = await axios.post<T>(url, formData);
  return data;
}

export const api = {
  // ---- Projects ----------------------------------------------------------
  listProjects: () => get<ProjectSummary[]>('/api/projects'),
  // Server-side search: matches project names AND conversation message content.
  searchProjects: (query: string) => get<ProjectSummary[]>('/api/projects/search', { q: query }),
  createProject: (name: string) => post<ProjectCreated>('/api/projects', { name }),
  renameProject: (projectId: string, name: string) =>
    put<ProjectSummary>(`/api/projects/${projectId}`, { name: name.trim() }),
  deleteProject: (projectId: string) =>
    del<ProjectDeleteResponse>(`/api/projects/${projectId}`),
  toggleProjectPin: (projectId: string, isPinned: boolean) =>
    put<ProjectSummary>(`/api/projects/${projectId}/pin`, { is_pinned: isPinned }),

  // ---- Requirement state --------------------------------------------------
  getProjectState: (projectId: string) =>
    get<RequirementStatePayload>(`/api/project/${projectId}`),
  updateProjectState: (projectId: string, updates: Record<string, unknown>) =>
    put<RequirementStatePayload>(`/api/project/${projectId}`, updates),

  // ---- Pending actions ----------------------------------------------------
  listPendingActions: (projectId: string) =>
    get<PendingActionPayload[]>(`/api/pending-actions/${projectId}`),
  confirmAction: (actionId: string, projectId: string) =>
    post<ConfirmActionResponse>(`/api/confirm-action/${actionId}`, null, { project_id: projectId }),
  cancelAction: (actionId: string, projectId: string) =>
    post<ActionStatusResponse>(`/api/cancel-action/${actionId}`, null, { project_id: projectId }),

  // ---- Artifact locks -----------------------------------------------------
  lockArtifact: (projectId: string, artifactType: string, artifactId: string, lockedBy = 'user') =>
    post<ArtifactLockResponse>(
      `/api/project/${projectId}/artifacts/${artifactType}/${artifactId}/lock`,
      { locked_by: lockedBy }
    ),
  unlockArtifact: (projectId: string, artifactType: string, artifactId: string, lockedBy = 'user') =>
    post<ArtifactLockResponse>(
      `/api/project/${projectId}/artifacts/${artifactType}/${artifactId}/unlock`,
      { locked_by: lockedBy }
    ),

  // ---- Multi-agent requirements workflow ----------------------------------
  // `signal` lets callers abort an in-flight generation (the Stop button) —
  // axios then rejects the promise with a CanceledError instead of waiting for
  // the LLM workflow to finish.
  processRequirements: (request: ProcessRequirementsRequest, signal?: AbortSignal) =>
    post<ProcessRequirementsResponse>('/api/process-requirements', request, undefined, signal),

  // ---- Generation cancellation (Stop button) --------------------------------
  // Asks the backend to hard-terminate the in-flight multi-agent run for a
  // project. Complements the AbortSignal above: the signal stops the UI
  // waiting, this stops the server actually doing the work.
  cancelProcessRequirements: (projectId: string) =>
    post<{ project_id: string; cancelled: boolean }>(
      '/api/process-requirements/cancel',
      null,
      { project_id: projectId },
    ),

  // ---- Clarifications ------------------------------------------------------
  submitClarifications: (projectId: string, answers: Record<string, string>) =>
    post<RequirementStatePayload>('/api/clarification/submit', {
      project_id: projectId,
      answers,
    }),

  // ---- Uploaded documents (knowledge base) ---------------------------------
  // Upload ONLY stores the converted markdown as knowledge; it never writes
  // requirements. `processDocument` is the explicit extraction action and
  // returns a DRAFT pending_action for user confirmation.
  uploadDocument: (projectId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return postFormData<UploadedDocumentPayload>(
      `/api/project/${projectId}/documents/upload`,
      formData,
    );
  },
  listDocuments: (projectId: string) =>
    get<UploadedDocumentPayload[]>(`/api/project/${projectId}/documents`),
  getDocumentMarkdown: (projectId: string, documentId: string) =>
    get<DocumentMarkdownPayload>(`/api/project/${projectId}/documents/${documentId}`),
  processDocument: (projectId: string, documentId: string) =>
    post<ProcessDocumentResponse>(
      `/api/project/${projectId}/documents/${documentId}/process`,
    ),

  // ---- Health --------------------------------------------------------------
  fetchHealth: () => get<HealthPayload>('/api/health'),
};
