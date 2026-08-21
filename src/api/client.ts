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
  HealthPayload,
  PendingActionPayload,
  ProcessRequirementsRequest,
  ProcessRequirementsResponse,
  ProjectCreated,
  ProjectDeleteResponse,
  ProjectSummary,
  RequirementStatePayload,
} from './types';

async function get<T>(url: string): Promise<T> {
  const { data } = await axios.get<T>(url);
  return data;
}

async function post<T>(url: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
  const { data } = await axios.post<T>(url, body ?? null, { params });
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

export const api = {
  // ---- Projects ----------------------------------------------------------
  listProjects: () => get<ProjectSummary[]>('/api/projects'),
  createProject: (name: string) => post<ProjectCreated>('/api/projects', { name }),
  renameProject: (projectId: string, name: string) =>
    put<ProjectSummary>(`/api/projects/${projectId}`, { name: name.trim() }),
  deleteProject: (projectId: string) =>
    del<ProjectDeleteResponse>(`/api/projects/${projectId}`),

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
  processRequirements: (request: ProcessRequirementsRequest) =>
    post<ProcessRequirementsResponse>('/api/process-requirements', request),

  // ---- Clarifications ------------------------------------------------------
  submitClarifications: (projectId: string, answers: Record<string, string>) =>
    post<RequirementStatePayload>('/api/clarification/submit', {
      project_id: projectId,
      answers,
    }),

  // ---- Health --------------------------------------------------------------
  fetchHealth: () => get<HealthPayload>('/api/health'),
};
