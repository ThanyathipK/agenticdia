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
  ConvertedPrdMarkdownPayload,
  DocumentMarkdownPayload,
  HealthPayload,
  PendingActionPayload,
  PrdSectionListPayload,
  PrdSectionUpdateResponse,
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

async function patch<T>(url: string, body?: unknown): Promise<T> {
  const { data } = await axios.patch<T>(url, body ?? {});
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

// Binary download helper — the JSON helpers above parse the body; file exports
// (LaTeX-compiled PDF / DOCX) must come back untouched as a Blob.
async function postBlob(url: string, body?: unknown): Promise<Blob> {
  const resp = await axios.post<Blob>(url, body ?? null, { responseType: 'blob' });
  return resp.data;
}

// Error bodies from binary endpoints arrive as a Blob too, so the FastAPI
// {"detail": ...} payload has to be decoded before it can be surfaced.
export async function detailFromBlobError(err: unknown): Promise<string | null> {
  if (!axios.isAxiosError(err) || !(err.response?.data instanceof Blob)) return null;
  try {
    const parsed = JSON.parse(await err.response.data.text()) as { detail?: unknown };
    return typeof parsed.detail === 'string' ? parsed.detail : null;
  } catch {
    return null;
  }
}

// Error bodies from JSON endpoints are FastAPI {"detail": ...} payloads: a
// plain string for 4xx conflicts (e.g. duplicate project name -> 409) or a
// list of issue objects for 422 validation failures, whose `msg` carries the
// readable text (Pydantic prefixes nested validator messages with
// "Value error, " — stripped here). Returns null when nothing usable exists.
export function detailFromJsonError(err: unknown): string | null {
  if (!axios.isAxiosError(err)) return null;
  const detail: unknown = (err.response?.data as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    for (const item of detail) {
      const msg = (item as { msg?: unknown })?.msg;
      if (typeof msg === 'string' && msg.trim()) {
        return msg.replace(/^Value error,\s*/i, '');
      }
    }
  }
  return null;
}

export const api = {
  // ---- PRD sections (part-level editing / locking / versioning) ------------
  // The PRD is stored as NINE editable parts; each part is independently
  // edited, locked, and versioned (append-only history).
  getPrdSections: (projectId: string) =>
    get<PrdSectionListPayload>(`/api/project/${projectId}/prd/sections`),
  updatePrdSection: (
    projectId: string,
    sectionKey: string,
    content: string,
    options?: { review_status?: string; change_summary?: string; updated_by?: string }
  ) =>
    patch<PrdSectionUpdateResponse>(`/api/project/${projectId}/prd/sections/${sectionKey}`, {
      content,
      review_status: options?.review_status,
      change_summary: options?.change_summary,
      updated_by: options?.updated_by ?? 'user',
    }),
  lockPrdSection: (projectId: string, sectionKey: string, lockedBy = 'user') =>
    post(`/api/project/${projectId}/prd/sections/${sectionKey}/lock`, { locked_by: lockedBy }),
  unlockPrdSection: (projectId: string, sectionKey: string, lockedBy = 'user') =>
    post(`/api/project/${projectId}/prd/sections/${sectionKey}/unlock`, { locked_by: lockedBy }),

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

  // ---- PRD template ---------------------------------------------------------
  // Official Krungsri Nimble PRD LaTeX template served from
  // backend/app/prompts/template-krungsrinimble.tex — the exact structure the
  // Architect agent fills in during generation. Normalized for the PRD panel
  // preview and compiled for exports.
  getPrdTemplate: () =>
    get<{ template_latex: string }>('/api/prd/template'),

  // ---- PRD preview normalization --------------------------------------------
  // The generated PRD body is LaTeX (Krungsri .tex template). The backend turns
  // either that LaTeX or a legacy Markdown PRD into clean GFM markdown so the
  // on-screen preview never renders raw LaTeX (POST /api/prd/convert).
  convertPrdToMarkdown: (source: string) =>
    post<ConvertedPrdMarkdownPayload>('/api/prd/convert', { latex_source: source }),

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

  // ---- PRD file export (LaTeX -> PDF / DOCX) --------------------------------
  // The generated PRD is LaTeX following template-krungsrinimble.tex, so both
  // exports are COMPILED server-side (PDF via Tectonic, DOCX via Pandoc) from
  // the current PRD document held in the store. The returned Blob is the
  // finished file — no client-side markdown parsing is involved.
  exportPrdPdf: (projectId: string, latexSource: string, version?: number, projectName?: string) =>
    postBlob(`/api/project/${projectId}/export/pdf`, {
      latex_source: latexSource,
      version,
      project_name: projectName,
    }),
  exportPrdDocx: (projectId: string, latexSource: string, version?: number, projectName?: string) =>
    postBlob(`/api/project/${projectId}/export/docx`, {
      latex_source: latexSource,
      version,
      project_name: projectName,
    }),

  // ---- Health --------------------------------------------------------------
  fetchHealth: () => get<HealthPayload>('/api/health'),
};
