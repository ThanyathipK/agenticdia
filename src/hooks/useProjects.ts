// useProjects — project list management extracted from the former
// useProjectState god-hook. Owns the project collection, the active project
// selection, pending merge actions, and the sidebar rename/delete/create
// interactions. All backend calls go through the typed `api` client.
import { useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api, detailFromJsonError } from '../api/client';
import type { PendingActionPayload, ProjectStatus, ProjectSummary } from '../api/types';
import { handleError } from '../components/Toast';

export interface ProjectContextMenuState {
  projectId: string;
  x: number;
  y: number;
}

export interface UseProjectsResult {
  projectId: string | null;
  setProjectId: Dispatch<SetStateAction<string | null>>;
  projects: ProjectSummary[];
  setProjects: Dispatch<SetStateAction<ProjectSummary[]>>;
  pendingActions: PendingActionPayload[];
  setPendingActions: Dispatch<SetStateAction<PendingActionPayload[]>>;
  projectContextMenu: ProjectContextMenuState | null;
  setProjectContextMenu: Dispatch<SetStateAction<ProjectContextMenuState | null>>;
  renameProjectId: string | null;
  setRenameProjectId: Dispatch<SetStateAction<string | null>>;
  renameProjectName: string;
  setRenameProjectName: Dispatch<SetStateAction<string>>;
  handleRenameProject: (projectId: string, newName: string) => Promise<void>;
  /** Deletes a project; resolves to true on success. */
  handleDeleteProject: (projIdToDelete: string) => Promise<boolean>;
  /**
   * Creates a project with the given name. Resolves to null on success (the
   * caller may close its dialog), or to a user-facing error message — e.g. a
   * duplicate-name conflict from the backend — for inline display.
   */
  handleCreateProject: (name: string) => Promise<string | null>;
  handleTogglePin: (projectId: string) => Promise<void>;
  /** Flags/unflags a project (dashboard ★ marker) — independent of pinning. */
  handleToggleFlag: (projectId: string) => Promise<void>;
  /** Sets the project's user-editable workflow status (dashboard table), optimistically. */
  handleUpdateProjectStatus: (projectId: string, status: ProjectStatus) => Promise<void>;
  /** Whether the styled "New Project" modal is shown (replaces native prompt()). */
  isCreateModalOpen: boolean;
  setIsCreateModalOpen: Dispatch<SetStateAction<boolean>>;
  /** Project awaiting delete confirmation in the styled ConfirmModal (replaces native confirm()). */
  projectPendingDelete: string | null;
  setProjectPendingDelete: Dispatch<SetStateAction<string | null>>;
  /** Sidebar search — matches projects by name OR by their conversation message content. */
  projectSearchQuery: string;
  setProjectSearchQuery: Dispatch<SetStateAction<string>>;
}

export function useProjects(): UseProjectsResult {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [pendingActions, setPendingActions] = useState<PendingActionPayload[]>([]);

  // Load the project list once on mount. The backend may still be booting, so
  // retry a few times before giving up (mirrors the original hook behavior).
  useEffect(() => {
    let isMounted = true;
    const fetchProjects = async (retries = 8, delay = 1000) => {
      try {
        const projs = await api.listProjects();
        if (isMounted) {
          setProjects(projs);
          if (projs.length > 0) {
            setProjectId(prev => (prev && projs.some(p => p.id === prev)) ? prev : projs[0].id);
          }
        }
      } catch (error) {
        if (retries > 0 && isMounted) {
          setTimeout(() => fetchProjects(retries - 1, delay), delay);
        } else {
          handleError('Failed to load projects from the server. Please check your connection.', error);
        }
      }
    };
    fetchProjects();
    return () => { isMounted = false; };
  }, []);

  // "New Project" modal visibility (the styled replacement for prompt()).
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);

  // Project awaiting delete confirmation in the styled ConfirmModal
  // (the styled replacement for confirm()). Holds the target project id.
  const [projectPendingDelete, setProjectPendingDelete] = useState<string | null>(null);

  // Context menu state for project rename/delete
  const [projectContextMenu, setProjectContextMenu] = useState<ProjectContextMenuState | null>(null);
  const [renameProjectId, setRenameProjectId] = useState<string | null>(null);
  const [renameProjectName, setRenameProjectName] = useState<string>('');

  // Sidebar project search. The query drives a debounced server search below;
  // matching happens against project names AND conversation message content.
  const [projectSearchQuery, setProjectSearchQuery] = useState<string>('');

  // Debounced server search: matches project names AND persisted conversation
  // message content (GET /api/projects/search). Clearing the query restores
  // the full list. A monotonic sequence guard drops stale responses so a slow
  // earlier request can never overwrite fresher results.
  const searchStateRef = useRef<{ searching: boolean; seq: number }>({ searching: false, seq: 0 });

  useEffect(() => {
    const query = projectSearchQuery.trim();

    // Query emptied -> restore the unfiltered list, but only after a search
    // actually replaced it (keeps the mount-time load untouched).
    if (!query) {
      if (!searchStateRef.current.searching) return;
      searchStateRef.current.searching = false;
      const seq = ++searchStateRef.current.seq;
      api.listProjects()
        .then((projs) => {
          if (searchStateRef.current.seq === seq) setProjects(projs);
        })
        .catch(() => {
          // Keep showing whatever is loaded; the next keystroke retries.
        });
      return;
    }

    const timer = setTimeout(() => {
      const seq = ++searchStateRef.current.seq;
      searchStateRef.current.searching = true;
      api.searchProjects(query)
        .then((results) => {
          if (searchStateRef.current.seq === seq) setProjects(results);
        })
        .catch((err) => {
          handleError('Failed to search projects.', err);
        });
    }, 250);
    return () => clearTimeout(timer);
  }, [projectSearchQuery]);

  // Close context menu on outside click
  useEffect(() => {
    const handleClick = () => setProjectContextMenu(null);
    if (projectContextMenu) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [projectContextMenu]);

  // Handle project rename. Failures — including the backend's 409
  // duplicate-name conflict — surface the server's own detail message in the
  // toast so the user knows exactly which name is already taken.
  const handleRenameProject = async (projectId: string, newName: string) => {
    if (!newName.trim()) return;
    try {
      await api.renameProject(projectId, newName);
      setProjects(prev => prev.map(p => (p.id === projectId ? { ...p, name: newName.trim() } : p)));
      setRenameProjectId(null);
      setRenameProjectName('');
    } catch (err) {
      handleError(detailFromJsonError(err) ?? 'Failed to rename the project.', err);
    }
  };

  // Handle project delete (submit from the styled ConfirmModal). Resolves to
  // true on success so the modal knows whether to close; failures are
  // surfaced through the toast handler.
  const handleDeleteProject = async (projIdToDelete: string): Promise<boolean> => {
    try {
      await api.deleteProject(projIdToDelete);
      setProjects(prev => prev.filter(p => p.id !== projIdToDelete));
      // If the deleted project was the active one, switch to the first remaining project
      if (projIdToDelete === projectId && projects.length > 1) {
        const remaining = projects.filter(p => p.id !== projIdToDelete);
        setProjectId(remaining[0].id);
      } else if (projIdToDelete === projectId) {
        setProjectId(null);
      }
      setProjectContextMenu(null);
      return true;
    } catch (err) {
      handleError('Failed to delete the project.', err);
      return false;
    }
  };

  // Handle project create (submit from the sidebar's New Project modal).
  // Resolves to null on success so the modal closes, or to a user-facing
  // error message — typically the backend's 409 "name already exists" detail —
  // that the modal renders inline next to the input. No toast here: the modal
  // is the presentation layer for create failures.
  const handleCreateProject = async (name: string): Promise<string | null> => {
    const trimmed = name.trim();
    if (!trimmed) return 'Project name must not be empty.';
    if (trimmed.length > 40) return 'Project name must be 40 characters or fewer.';
    try {
      await api.createProject(trimmed);
      setProjects(await api.listProjects());
      return null;
    } catch (err) {
      return detailFromJsonError(err) ?? 'Failed to create the project.';
    }
  };

  // Handle project pin/unpin — pins the chat to the top of the sidebar.
  const handleTogglePin = async (projectIdToPin: string) => {
    const target = projects.find(p => p.id === projectIdToPin);
    const nextPinned = !(target && target.is_pinned);
    // Optimistic update for snappy UI, then reconcile with the server.
    setProjects(prev =>
      prev.map(p => (p.id === projectIdToPin ? { ...p, is_pinned: nextPinned } : p))
    );
    try {
      const updated = await api.toggleProjectPin(projectIdToPin, nextPinned);
      setProjects(prev => prev.map(p => (p.id === projectIdToPin ? { ...p, is_pinned: updated.is_pinned } : p)));
    } catch (err) {
      setProjects(prev =>
        prev.map(p => (p.id === projectIdToPin ? { ...p, is_pinned: !nextPinned } : p))
      );
      handleError('Failed to update the pin.', err);
    }
    setProjectContextMenu(null);
  };

  // Handle project flag/unflag — dashboard-only ★ marker. Deliberately
  // independent of pinning: flagging marks the project for attention in the
  // projects overview table and never affects the sidebar's pinned ordering.
  const handleToggleFlag = async (projectIdToFlag: string) => {
    const target = projects.find(p => p.id === projectIdToFlag);
    const nextFlagged = !(target && target.is_flagged);
    // Optimistic update for snappy UI, then reconcile with the server.
    setProjects(prev =>
      prev.map(p => (p.id === projectIdToFlag ? { ...p, is_flagged: nextFlagged } : p))
    );
    try {
      const updated = await api.toggleProjectFlag(projectIdToFlag, nextFlagged);
      setProjects(prev => prev.map(p => (p.id === projectIdToFlag ? { ...p, is_flagged: updated.is_flagged } : p)));
    } catch (err) {
      setProjects(prev =>
        prev.map(p => (p.id === projectIdToFlag ? { ...p, is_flagged: !nextFlagged } : p))
      );
      handleError('Failed to update the flag.', err);
    }
    setProjectContextMenu(null);
  };

  // Handle project workflow status change (dashboard status badge dropdown).
  // Same optimistic pattern as pinning: apply locally for snappy UI, reconcile
  // with the server, and roll back on failure with a toast.
  const handleUpdateProjectStatus = async (projectIdToUpdate: string, newStatus: ProjectStatus) => {
    const previousStatus = projects.find(p => p.id === projectIdToUpdate)?.status;
    setProjects(prev =>
      prev.map(p => (p.id === projectIdToUpdate ? { ...p, status: newStatus } : p))
    );
    try {
      const updated = await api.updateProjectStatus(projectIdToUpdate, newStatus);
      setProjects(prev =>
        prev.map(p => (p.id === projectIdToUpdate ? { ...p, status: updated.status, updated_at: updated.updated_at } : p))
      );
    } catch (err) {
      setProjects(prev =>
        prev.map(p => (p.id === projectIdToUpdate ? { ...p, status: previousStatus } : p))
      );
      handleError('Failed to update the project status.', err);
    }
    setProjectContextMenu(null);
  };

  return {
    projectId,
    setProjectId,
    projects,
    setProjects,
    pendingActions,
    setPendingActions,
    projectContextMenu,
    setProjectContextMenu,
    renameProjectId,
    setRenameProjectId,
    renameProjectName,
    setRenameProjectName,
    handleRenameProject,
    handleDeleteProject,
    handleCreateProject,
    handleTogglePin,
    handleToggleFlag,
    handleUpdateProjectStatus,
    isCreateModalOpen,
    setIsCreateModalOpen,
    projectPendingDelete,
    setProjectPendingDelete,
    projectSearchQuery,
    setProjectSearchQuery,
  };
}