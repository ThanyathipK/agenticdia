// useProjects — project list management extracted from the former
// useProjectState god-hook. Owns the project collection, the active project
// selection, pending merge actions, and the sidebar rename/delete/create
// interactions. All backend calls go through the typed `api` client.
import { useEffect, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import { api } from '../api/client';
import type { PendingActionPayload, ProjectSummary } from '../api/types';
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
  handleDeleteProject: (projIdToDelete: string) => Promise<void>;
  handleCreateProject: () => Promise<void>;
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

  // Context menu state for project rename/delete
  const [projectContextMenu, setProjectContextMenu] = useState<ProjectContextMenuState | null>(null);
  const [renameProjectId, setRenameProjectId] = useState<string | null>(null);
  const [renameProjectName, setRenameProjectName] = useState<string>('');

  // Close context menu on outside click
  useEffect(() => {
    const handleClick = () => setProjectContextMenu(null);
    if (projectContextMenu) {
      document.addEventListener('click', handleClick);
      return () => document.removeEventListener('click', handleClick);
    }
  }, [projectContextMenu]);

  // Handle project rename
  const handleRenameProject = async (projectId: string, newName: string) => {
    if (!newName.trim()) return;
    try {
      await api.renameProject(projectId, newName);
      setProjects(prev => prev.map(p => (p.id === projectId ? { ...p, name: newName.trim() } : p)));
      setRenameProjectId(null);
      setRenameProjectName('');
    } catch (err) {
      handleError('Failed to rename the project.', err);
    }
  };

  // Handle project delete
  const handleDeleteProject = async (projIdToDelete: string) => {
    if (!confirm('Are you sure you want to delete this project? This action cannot be undone.')) return;
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
    } catch (err) {
      handleError('Failed to delete the project.', err);
    }
  };

  // Handle project create (used by the sidebar "new project" button)
  const handleCreateProject = async () => {
    const name = prompt('Enter project name:');
    if (name) {
      try {
        await api.createProject(name);
        setProjects(await api.listProjects());
      } catch (err) {
        handleError('Failed to create the project.', err);
      }
    }
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
  };
}