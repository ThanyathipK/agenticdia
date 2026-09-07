import { useState } from 'react';
import { GitCommit } from 'lucide-react';
import {
  UserRow,
  RequirementRow,
  UserStoryRow,
  AcceptanceCriterionRow,
  VersionHistoryRow,
  INITIAL_USERS,
  INITIAL_REQUIREMENTS,
} from '../../data';
import { notify } from '../Toast';

interface SnapshotLedgerProps {
  requirements: RequirementRow[];
  users: UserRow[];
  userStories: UserStoryRow[];
  criteria: AcceptanceCriterionRow[];
  versions: VersionHistoryRow[];
  setRequirements: React.Dispatch<React.SetStateAction<RequirementRow[]>>;
  setVersions: React.Dispatch<React.SetStateAction<VersionHistoryRow[]>>;
  getRequirementTitle: (id: string) => string;
  getProjectName: (id: string) => string;
  getUserName: (id: string) => string;
}

/**
 * TAB: IMMUTABLE VERSION SNAPSHOT LEDGER
 * Owns the snapshot-capture form and renders the browser-local snapshot
 * ledger. Capturing a snapshot deep-exports the linked user stories (and
 * acceptance criteria) into a simulated JSONB state block and increments the
 * target requirement's version number.
 *
 * NOTE: this tab is a frontend demo. The historical `version_history` table
 * was removed from the schema (no runtime read/write path existed); the
 * authoritative immutable ledger is `prd_versions`.
 */
export default function SnapshotLedger({
  requirements,
  users,
  userStories,
  criteria,
  versions,
  setRequirements,
  setVersions,
  getRequirementTitle,
  getProjectName,
  getUserName,
}: SnapshotLedgerProps) {
  // Snapshot Creation state
  const [snapshotForm, setSnapshotForm] = useState({
    requirementId: INITIAL_REQUIREMENTS[0].id,
    authorId: INITIAL_USERS[0].id,
    changeDescription: 'Verified system boundaries and secured regulatory OTP flows.'
  });

  // Capture Version History Snapshot
  const handleCaptureSnapshot = (e: React.FormEvent) => {
    e.preventDefault();
    
    const relatedReq = requirements.find(r => r.id === snapshotForm.requirementId);
    if (!relatedReq) return;

    // Filter stories linked to this epic to create the immutable state snapshot
    const linkedStories = userStories.filter(s => s.requirement_id === relatedReq.id);
    const linkedStoriesSnap = linkedStories.map(s => {
      const relatedAc = criteria.filter(ac => ac.user_story_id === s.id);
      return {
        ticket: s.ticket_code,
        title: s.story_title,
        as_a: s.as_a,
        i_want_to: s.i_want_to,
        so_that: s.so_that,
        acceptance_criteria: relatedAc.map(a => a.criteria_text)
      };
    });

    const nextVersion = relatedReq.version + 1;
    const newSnapshotId = crypto.randomUUID();

    const newVersionLog: VersionHistoryRow = {
      id: newSnapshotId,
      project_id: relatedReq.project_id,
      requirement_id: relatedReq.id,
      version_number: nextVersion,
      changed_by_user_id: snapshotForm.authorId,
      change_description: snapshotForm.changeDescription,
      state_snapshot: JSON.stringify({
        captured_at: new Date().toISOString(),
        requirement_title: relatedReq.title,
        requirement_code: relatedReq.requirement_code,
        user_stories: linkedStoriesSnap
      }),
      created_at: new Date().toISOString().replace('Z', '+00')
    };

    // Update requirements state: increment version number
    setRequirements(prev => prev.map(r => r.id === relatedReq.id ? { ...r, version: nextVersion } : r));
    // Append to version ledger
    setVersions([newVersionLog, ...versions]);

    notify(`Snapshot Captured! Mapped ${linkedStories.length} stories into immutable JSONB Ledger.`, 'success');
  };

  return (
    <div className="space-y-6">
      
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <h3 className="text-sm font-bold text-slate-900 mb-2">Immutable JSONB State Snapshot Capture</h3>
        <p className="text-xs text-slate-500 mb-6">
          Agile requirements are prone to scope-creep and audit failures. In accordance with compliance models, the system forces a deep snapshot export on each approved iteration.
        </p>

        <form onSubmit={handleCaptureSnapshot} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Target Epic (requirement_id)</label>
              <select 
                value={snapshotForm.requirementId}
                onChange={e => setSnapshotForm({ ...snapshotForm, requirementId: e.target.value })}
                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
              >
                  {requirements.map(r => (
                    <option key={r.id} value={r.id}>{r.title} (v{r.version})</option>
                  ))}
              </select>
            </div>
<div>
              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Authorized Author (changed_by)</label>
              <select 
                value={snapshotForm.authorId}
                onChange={e => setSnapshotForm({ ...snapshotForm, authorId: e.target.value })}
                className="w-full bg-white border border-slate-300 rounded-xl p-2 text-xs focus:outline-none focus:border-navy-600"
              >
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name} ({u.role})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Capture Action</label>
              <button
                type="submit"
                className="w-full py-2 bg-navy-600 hover:bg-navy-700 text-white font-semibold rounded-xl text-xs flex items-center justify-center gap-1.5 transition-colors cursor-pointer shadow shadow-navy-500/20"
              >
                <GitCommit className="w-4 h-4" />
                <span>Capture State Snapshot</span>
              </button>
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-bold text-slate-500 uppercase mb-1">Change Control Log & Description</label>
            <input 
              type="text" 
              required
              value={snapshotForm.changeDescription}
              onChange={e => setSnapshotForm({ ...snapshotForm, changeDescription: e.target.value })}
              placeholder="e.g., Aligned criteria with national clearing thresholds and added fallback loops."
              className="w-full bg-white border border-slate-300 rounded-xl p-2.5 text-xs focus:outline-none focus:border-navy-600"
            />
          </div>
        </form>
      </div>

      {/* Historical logs render */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <h3 className="text-sm font-bold text-slate-900 mb-4">Immutable Ledger History (demo — see prd_versions)</h3>
<div className="space-y-4">
          {versions.map((ver) => {
            const snap = JSON.parse(ver.state_snapshot);
            return (
              <div key={ver.id} className="border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
                <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex justify-between items-center text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono bg-navy-50 text-navy-700 border border-navy-200 px-2 py-0.5 rounded font-bold uppercase">
                      VERSION {ver.version_number}.0
                    </span>
                    <span className="text-slate-400 font-mono">|</span>
                    <span className="font-sans text-slate-600 font-semibold">Requirement: {getRequirementTitle(ver.requirement_id)}</span>
                  </div>
                  <span className="font-mono text-slate-400 text-[11px]">
                    Posted: {ver.created_at}
                  </span>
                </div>

                <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                  <div className="md:col-span-2 space-y-2">
                    <div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase block">Log Entry Description</span>
                      <p className="text-slate-800 font-medium">{ver.change_description}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-4 pt-1">
                      <div>
                        <span className="text-[10px] font-bold text-slate-400 uppercase block">Project Context</span>
                        <p className="text-slate-700 font-medium">{getProjectName(ver.project_id)}</p>
                      </div>
                      <div>
                        <span className="text-[10px] font-bold text-slate-400 uppercase block">Committed By</span>
                        <p className="text-slate-700 font-medium">{getUserName(ver.changed_by_user_id)}</p>
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-950 p-3.5 rounded-xl border border-slate-800 font-mono text-[10px] text-slate-300">
                    <span className="text-[9px] text-navy-400 font-bold uppercase block mb-1">Postgres JSONB State</span>
                    <pre className="max-h-24 overflow-y-auto overflow-x-hidden whitespace-pre-wrap leading-tight text-slate-400">
                      {JSON.stringify(snap, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
}