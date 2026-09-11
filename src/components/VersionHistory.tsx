// VersionHistory
// Renders the immutable change ledger timeline and diff viewer.
import { useEffect, useState } from "react";
import { GitCompare, Plus, Minus, Lock, FileText } from "lucide-react";
import { ProjectState } from "../hooks/useProjectState";
import { api } from "../api/client";
import type { PrdVersionDiffPayload, PrdVersionDiffSectionPayload } from "../api/types";

/** Renders diff lines: green for additions, red for deletions, grey for context. */
function DiffLines({ diffLines }: { diffLines: [string, string][] }) {
  if (diffLines.length === 0) {
    return <span className="text-slate-400 italic text-xs">(no line changes)</span>;
  }
  return (
    <div className="font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">
      {diffLines.map(([tag, line], idx) => {
        let cls = 'px-2 py-0.5 rounded-md border-l-2 flex';
        if (tag === 'add') cls += ' bg-emerald-50 text-emerald-800 border-emerald-400';
        else if (tag === 'del') cls += ' bg-red-50 text-red-800 border-red-400';
        else cls += ' text-slate-600 border-slate-200';
        const prefix = tag === 'add' ? '+' : tag === 'del' ? '-' : ' ';
        const lineCls = tag === 'add' ? 'text-emerald-700 font-semibold' : tag === 'del' ? 'text-red-700 font-semibold' : 'text-slate-500';
        return (
          <div key={idx} className={cls}>
            <span className="inline-block w-5 mr-2 text-center select-none font-bold">{prefix}</span>
            <span className={lineCls}>{line}</span>
          </div>
        );
      })}
    </div>
  );
}

/** One per-section diff card showing title, change kind, line counts and diff. */
function SectionDiffCard({ section }: {
  section: PrdVersionDiffSectionPayload;
}) {
  const kindBorder = {
    created: 'border-emerald-300 bg-emerald-50/40',
    updated: 'border-blue-300 bg-blue-50/40',
    unchanged: 'border-slate-200 bg-slate-50/30',
    removed: 'border-red-300 bg-red-50/40',
    locked_preserved: 'border-amber-300 bg-amber-50/40',
  }[section.change_kind] ?? 'border-slate-200 bg-slate-50/30';

  const kindLabel = {
    created: 'New Section',
    updated: 'Updated',
    unchanged: 'Unchanged',
    removed: 'Removed',
    locked_preserved: 'Locked (Preserved)',
  }[section.change_kind] ?? section.change_kind;

  return (
    <div className={"rounded-xl border-2 p-4 " + kindBorder}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {section.change_kind === 'locked_preserved' ? (
            <Lock className="w-3.5 h-3.5 flex-shrink-0 text-amber-500" />
          ) : section.change_kind === 'removed' ? (
            <Minus className="w-3.5 h-3.5 flex-shrink-0 text-red-500" />
          ) : section.change_kind === 'created' ? (
            <Plus className="w-3.5 h-3.5 flex-shrink-0 text-emerald-500" />
          ) : (
            <FileText className="w-3.5 h-3.5 flex-shrink-0 text-slate-400" />
          )}
          <div className="min-w-0">
            <h5 className="font-semibold text-sm truncate">{section.title}</h5>
            <p className="text-[10px] font-mono opacity-70">{section.section_key}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-black/5">{kindLabel}</span>
          {section.changed && section.change_kind !== 'unchanged' && section.change_kind !== 'locked_preserved' && (
            <div className="flex items-center gap-1.5 text-[11px] font-mono">
              {section.added > 0 && <span className="text-emerald-600 font-semibold">+{section.added}</span>}
              {section.removed > 0 && <span className="text-red-600 font-semibold">-{section.removed}</span>}
              <span className="text-slate-400">lines</span>
            </div>
          )}
        </div>
      </div>
      {section.change_kind === 'created' && section.diff_lines.length > 0 && (
        <div className="mt-2"><DiffLines diffLines={section.diff_lines} /></div>
      )}
      {section.change_kind === 'updated' && section.diff_lines.length > 0 && (
        <div className="mt-2 border-t border-black/5 pt-2"><DiffLines diffLines={section.diff_lines} /></div>
      )}
      {section.change_kind === 'removed' && section.diff_lines.length > 0 && (
        <div className="mt-2"><DiffLines diffLines={section.diff_lines} /></div>
      )}
      {section.change_kind === 'locked_preserved' && (
        <p className="text-xs text-amber-700 mt-1">
          The section was locked - content preserved despite AI regeneration.
        </p>
      )}
      {section.change_kind === 'unchanged' && section.diff_lines.length === 0 && (
        <p className="text-xs text-slate-400 mt-1">No changes to this section.</p>
      )}
    </div>
  );
}

function ChangeTypeBadge({ changeType }: { changeType: string | undefined }) {
  if (!changeType) return null;
  return (
    <span className={"text-[10px] font-bold px-1.5 py-0.5 rounded " + (changeType === 'ai' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700')}>
      {changeType === 'ai' ? 'AI' : 'Manual'}
    </span>
  );
}

export function VersionHistory({ state }: { state: ProjectState }) {
  const {
    versionHistory,
    selectedHistVersion,
    setSelectedHistVersion,
    projectId,
    diffBaseVersion,
    setDiffBaseVersion,
  } = state;

  // Auto-select the latest version whenever the history changes — the diff
  // should always compare the most recent snapshot against its predecessor.
  useEffect(() => {
    if (versionHistory.length > 0) {
      const latest = versionHistory[0].version; // newest first
      console.log('[Diff] Auto-selected latest version:', latest, '(history:', versionHistory.length, 'versions)');
      if (selectedHistVersion !== latest) setSelectedHistVersion(latest);
    }
  }, [versionHistory, setSelectedHistVersion]);

  // Auto-set base version to the immediate predecessor of the selected version.
  useEffect(() => {
    if (!projectId || selectedHistVersion <= 1) { setDiffBaseVersion(null); return; }
    // Find the version immediately before the selected one (any sort order).
    const sorted = [...versionHistory].sort((a, b) => a.version - b.version);
    const idx = sorted.findIndex(v => v.version === selectedHistVersion);
    if (idx > 0) setDiffBaseVersion(sorted[idx - 1].version);
    else setDiffBaseVersion(null);
  }, [selectedHistVersion, versionHistory, projectId, setDiffBaseVersion]);

  const [diff, setDiff] = useState<PrdVersionDiffPayload | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId || selectedHistVersion < 1) return;
    const base = diffBaseVersion ?? undefined;
    if (selectedHistVersion === 1 || !base || base === selectedHistVersion) {
      setDiff(null); setDiffError(null); return;
    }
    console.log('[Diff] Fetching diff:', projectId, 'v' + selectedHistVersion, 'vs v' + base);
    setDiffLoading(true);
    setDiffError(null);
    api.getPrdVersionDiff(projectId, selectedHistVersion, base)
      .then(result => {
        console.log('[Diff] Received:', result.sections?.length, 'sections');
        setDiff(result);
      })
      .catch(err => {
        console.warn('[Diff] Error:', err);
        // Don't show 404 as an error — it just means there's nothing to compare
        if (String(err).includes('404')) {
          setDiff(null);
          setDiffError(null);
        } else {
          setDiffError(String(err));
        }
      })
      .finally(() => setDiffLoading(false));
  }, [projectId, selectedHistVersion, diffBaseVersion]);

  const selected = versionHistory.find(v => v.version === selectedHistVersion);
  const base = diffBaseVersion != null ? versionHistory.find(v => v.version === diffBaseVersion) : null;
  const totalAdded = diff ? diff.sections.reduce((a: number, s: PrdVersionDiffSectionPayload) => a + s.added, 0) : 0;
  const totalRemoved = diff ? diff.sections.reduce((a: number, s: PrdVersionDiffSectionPayload) => a + s.removed, 0) : 0;
  const changedSections = diff ? diff.sections.filter(s => s.changed).length : 0;

  return (
    <div className="space-y-6 animate-fadeIn">
      <div className="bg-white rounded-3xl border border-outline p-6 shadow-sm">
        <h3 className="font-bold text-sm text-on-surface mb-6 flex items-center gap-2">
          <GitCompare className="text-primary w-4.5 h-4.5" />
          <span>Requirements Immutable Change Ledger</span>
        </h3>
        <div className="relative border-l-2 border-primary/20 pl-8 ml-4 space-y-8 pb-4">
          {versionHistory.map((v, idx) => (
            <div key={idx} className="relative">
              <button
                onClick={() => setSelectedHistVersion(v.version)}
                className={"absolute -left-12 w-8 h-8 rounded-full border-2 flex items-center justify-center font-mono text-xs font-bold transition-all " +
                  (selectedHistVersion === v.version
                    ? 'bg-primary border-primary text-on-primary scale-110 shadow-md shadow-primary/20'
                    : 'bg-white border-outline text-on-surface-variant hover:border-primary/50')}
              >
                v{v.semVersion || `${v.version}.0`}
              </button>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-on-surface">Snapshot {v.semVersion || `#${v.version}.0`}</span>
                  <span className="text-[10.5px] font-mono text-on-surface-variant bg-black/5 px-2 py-0.5 rounded">{v.timestamp}</span>
                  <ChangeTypeBadge changeType={v.changeType} />
                </div>
                <p className="text-xs text-on-surface-variant leading-relaxed">
                  Captured by: <strong className="text-on-surface font-semibold">{v.author}</strong> — <em>"{v.description}"</em>
                </p>
              </div>
            </div>
          ))}

        </div>

        {versionHistory.length === 0 && (
          <p className="text-sm text-on-surface-variant italic py-4 text-center">
            No version history yet. Generate a PRD to start tracking changes.
          </p>
        )}

        {selected && base && (
          <div className="flex items-center gap-4 mb-4 px-4 py-3 bg-slate-50 rounded-xl border border-slate-200">
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">From:</span>
              <span className="text-sm font-bold text-slate-700">v{base.semVersion || `${base.version}.0`}</span>
              <span className="text-xs text-slate-400">({base.timestamp})</span>
            </div>
            <div className="text-slate-300 text-xs">→</div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-500">To:</span>
              <span className="text-sm font-bold text-slate-700">v{selected.semVersion || `${selected.version}.0`}</span>
              <span className="text-xs text-slate-400">({selected.timestamp})</span>
            </div>
            {diff && (
              <div className="ml-auto flex items-center gap-3 text-xs font-mono">
                {totalAdded > 0 && <span className="text-emerald-600 font-semibold">+{totalAdded} lines added</span>}
                {totalRemoved > 0 && <span className="text-red-600 font-semibold">-{totalRemoved} lines removed</span>}
                {changedSections > 0 && <span className="text-slate-400">·</span>}
                {changedSections > 0 && <span className="text-slate-500">{changedSections} sections changed</span>}
              </div>
            )}
          </div>
        )}

        {diffLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="flex items-center gap-2 text-sm text-on-surface-variant">
              <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
              Loading diff...
            </div>
          </div>
        )}

        {diffError && (
          <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
            <Minus className="w-4 h-4 flex-shrink-0" />
            Could not load diff: {diffError}
          </div>
        )}

        {!diffLoading && !diffError && diff && (
          <div className="space-y-4">
            {diff.sections.length === 0 ? (
              <p className="text-sm text-on-surface-variant italic py-8 text-center">No differences found between these versions.</p>
            ) : (
              diff.sections.map((section) => (
                <SectionDiffCard key={section.section_key} section={section} />
              ))
            )}
          </div>
        )}

        {!diffLoading && !diffError && !diff && selected && (
          <p className="text-sm text-on-surface-variant italic py-8 text-center">
            {selected.version === 1
              ? 'This is the first version — nothing to compare against yet.'
              : 'Select a prior version as the baseline to see the diff.'}
          </p>
        )}

        <div className="flex items-center gap-4 mt-6 pt-4 border-t border-black/5 text-[10px] text-on-surface-variant">
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded bg-emerald-50 border border-emerald-300" />
            Added lines
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded bg-red-50 border border-red-300" />
            Removed lines
          </div>
          <div className="flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 rounded bg-slate-100 border border-slate-300" />
            Unchanged context
          </div>
          <div className="flex items-center gap-1.5">
            <Lock className="w-3 h-3 text-amber-500" />
            Locked (preserved)
          </div>
        </div>
      </div>
    </div>
  );
}
