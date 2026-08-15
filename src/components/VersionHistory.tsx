// VersionHistory — Version Ledger tab extracted from the former Dashboard.tsx.
// Renders the immutable change ledger timeline and the differential log viewer.
import { GitCompare } from 'lucide-react';
import { ProjectState } from '../hooks/useProjectState';

export function VersionHistory({ state }: { state: ProjectState }) {
  const {
    versionHistory,
    selectedHistVersion,
    setSelectedHistVersion,
    projectId,
  } = state;

  return (
    <div className="space-y-6 animate-fadeIn">
      
      {/* Timeline Selection Stage */}
      <div className="bg-white rounded-3xl border border-outline p-6 shadow-sm">
        <h3 className="font-bold text-sm text-on-surface mb-6 flex items-center gap-2">
          <GitCompare className="text-primary w-4.5 h-4.5" />
          <span>Requirements Immutable Change Ledger</span>
        </h3>

        {/* Timeline chain */}
        <div className="relative border-l-2 border-primary/20 pl-8 ml-4 space-y-8 pb-4">
          {versionHistory.map((v, idx) => (
            <div key={idx} className="relative">
              {/* Version indicator bubble */}
              <button
                onClick={() => setSelectedHistVersion(v.version)}
                className={`absolute -left-12 w-8 h-8 rounded-full border-2 flex items-center justify-center font-mono text-xs font-bold transition-all ${
                  selectedHistVersion === v.version
                    ? 'bg-primary border-primary text-on-primary scale-110 shadow-md shadow-primary/20'
                    : 'bg-white border-outline text-on-surface-variant hover:border-primary/50'
                }`}
              >
                v{v.version}
              </button>

              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-on-surface">Snapshot Revision #{v.version}.0</span>
                  <span className="text-[10.5px] font-mono text-on-surface-variant bg-black/5 px-2 py-0.5 rounded">
                    {v.timestamp}
                  </span>
                </div>
                            <p className="text-xs text-on-surface-variant leading-relaxed">
                              Captured by: <strong className="text-on-surface font-semibold">{v.author}</strong> — <em>"{v.description}"</em>
                            </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Differential Log Viewer Pane */}
      <div className="bg-white rounded-3xl border border-outline p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-black/5">
          <div className="flex items-center gap-2">
            <GitCompare className="text-primary w-4.5 h-4.5" />
            <div>
              <h4 className="font-bold text-sm text-on-surface">Interactive Difference Analysis (Diff Log)</h4>
              <p className="text-[11px] text-on-surface-variant">Comparing: Revision v{selectedHistVersion}.0 against Baseline</p>
            </div>
          </div>
          <span className="text-[10px] bg-emerald-100 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded font-bold uppercase">
            Ledger Checked
          </span>
        </div>

        <div className="space-y-3">
          <div className="p-4 bg-slate-900 rounded-2xl border border-slate-800 font-mono text-xs text-slate-100 leading-relaxed">
            <div className="text-slate-500 mb-2">/* Differential modification summary */</div>
            {selectedHistVersion === 1 ? (
              <>
                <div className="text-emerald-400 font-semibold">+ INSERT INTO requirements (epic_name, version) VALUES ("PromptPay QR Settlement", 1);</div>
                <div className="text-emerald-400 font-semibold">+ INSERT INTO user_stories (ticket_code, story_title) VALUES ("US-001", "Real-time Fund Settlement");</div>
                <div className="text-slate-400">  -- Checklist status initialized. Checking compliance...</div>
              </>
            ) : (
              <>
                <div className="text-orange-400 font-semibold">- UPDATE requirements SET version = {selectedHistVersion - 1} WHERE id = '{projectId}';</div>
                <div className="text-emerald-400 font-semibold">+ UPDATE requirements SET version = {selectedHistVersion}, is_locked = TRUE WHERE id = '{projectId}';</div>
                <div className="text-emerald-400 font-semibold">+ INSERT INTO audit_results (passed_checks) VALUES ('Idempotency', 'Retry Strategy');</div>
                <div className="text-slate-400">  -- Requirements compliance validated. Compiled PRD Document finalized.</div>
              </>
            )}
          </div>
          <p className="text-xs text-on-surface-variant italic">
            Revision history states are saved as cryptographic JSONB payload structures in the database, allowing retroactive rollback safety.
          </p>
        </div>
      </div>

    </div>
  );
}