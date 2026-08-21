// useArtifactLocks — optimistic lock/unlock actions extracted from the former
// useProjectState god-hook. Works against the shared `RequirementStore` so lock
// state stays consistent with the rest of the requirement engine.
import { api } from '../api/client';
import type {
  ArtifactLockState,
  RequirementLockState,
} from '../components/types';
import { handleError } from '../components/Toast';
import type { RequirementStore } from './useRequirementStore';

export interface UseArtifactLocksResult {
  lockedArtifacts: Record<string, ArtifactLockState>;
  lockedRequirements: Record<string, RequirementLockState>;
  handleLockArtifact: (artifactType: string, artifactId: string, artifactCode: string) => Promise<void>;
  handleUnlockArtifact: (artifactType: string, artifactId: string, artifactCode: string) => Promise<void>;
  handleLockRequirement: (requirementCode: string) => Promise<void>;
  handleUnlockRequirement: (requirementCode: string) => Promise<void>;
}

export function useArtifactLocks(
  store: RequirementStore,
  projectId: string | null
): UseArtifactLocksResult {
  // Generic lock artifact function - ISOLATED, no full project reload
  const handleLockArtifact = async (artifactType: string, artifactId: string, artifactCode: string) => {
    if (!projectId) return;

    // Optimistic update - immediately update UI
    const optimisticLock: ArtifactLockState = {
      is_locked: true,
      locked_by: 'user',
      locked_at: new Date().toISOString(),
    };

    store.setLockedArtifacts(prev => ({
      ...prev,
      [artifactCode]: optimisticLock,
    }));

    if (artifactType === 'requirement') {
      store.setLockedRequirements(prev => ({
        ...prev,
        [artifactCode]: { ...optimisticLock, artifact_id: artifactId },
      }));
    }

    store.setSyncStatus(`${artifactType.replace('_', ' ')} ${artifactCode} locked.`);

    try {
      await api.lockArtifact(projectId, artifactType, artifactId, 'user');
      // Success - optimistic update already applied
    } catch (err) {
      // Rollback on failure
      handleError(`Failed to lock the ${artifactType}.`, err);
      store.setLockedArtifacts(prev => ({
        ...prev,
        [artifactCode]: { is_locked: false },
      }));
      if (artifactType === 'requirement') {
        store.setLockedRequirements(prev => ({
          ...prev,
          [artifactCode]: { is_locked: false, artifact_id: artifactId },
        }));
      }
      store.setSyncStatus(`Failed to lock ${artifactType}.`);
    }
  };

  // Generic unlock artifact function - ISOLATED, no full project reload
  const handleUnlockArtifact = async (artifactType: string, artifactId: string, artifactCode: string) => {
    if (!projectId) return;

    // Optimistic update - immediately update UI
    store.setLockedArtifacts(prev => ({
      ...prev,
      [artifactCode]: { is_locked: false },
    }));

    if (artifactType === 'requirement') {
      store.setLockedRequirements(prev => ({
        ...prev,
        [artifactCode]: { is_locked: false, artifact_id: artifactId },
      }));
    }

    store.setSyncStatus(`${artifactType.replace('_', ' ')} ${artifactCode} unlocked.`);

    try {
      await api.unlockArtifact(projectId, artifactType, artifactId, 'user');
      // Success - optimistic update already applied
    } catch (err) {
      // Rollback on failure
      handleError(`Failed to unlock the ${artifactType}.`, err);
      store.setLockedArtifacts(prev => ({
        ...prev,
        [artifactCode]: { is_locked: true },
      }));
      if (artifactType === 'requirement') {
        store.setLockedRequirements(prev => ({
          ...prev,
          [artifactCode]: { is_locked: true, artifact_id: artifactId },
        }));
      }
      store.setSyncStatus(`Failed to unlock ${artifactType}.`);
    }
  };

  // Legacy functions for backward compatibility
  const handleLockRequirement = async (requirementCode: string) => {
    const reqs = store.structuredRequirements.requirements || [];
    const req = reqs.find(r => r.requirement_code === requirementCode);
    if (!req) return;
    // Try to get ID from req.id or from lockedRequirements state
    const reqId = req.id || store.lockedRequirements[requirementCode]?.artifact_id;
    if (!reqId) return;
    await handleLockArtifact('requirement', reqId, requirementCode);
  };

  const handleUnlockRequirement = async (requirementCode: string) => {
    const reqs = store.structuredRequirements.requirements || [];
    const req = reqs.find(r => r.requirement_code === requirementCode);
    if (!req) return;
    // Try to get ID from req.id or from lockedRequirements state
    const reqId = req.id || store.lockedRequirements[requirementCode]?.artifact_id;
    if (!reqId) return;
    await handleUnlockArtifact('requirement', reqId, requirementCode);
  };

  return {
    lockedArtifacts: store.lockedArtifacts,
    lockedRequirements: store.lockedRequirements,
    handleLockArtifact,
    handleUnlockArtifact,
    handleLockRequirement,
    handleUnlockRequirement,
  };
}