// PRDEditor — PRD Document tab extracted from the former Dashboard.tsx.
// Renders the compiled PRD as editable markdown sections with lock/unlock and
// inline section editing.
import { useRef } from 'react';
import { FileText, Pencil, Save, Lock, Unlock } from 'lucide-react';
import { ProjectState } from '../hooks/useProjectState';
import { getSafeSectionTitle, getSafeSectionContent } from '../utils/markdown';
import { parseAndRenderMarkdown } from './MarkdownRenderer';

export function PRDEditor({ state }: { state: ProjectState }) {
  const {
    prdMarkdown,
    sections,
    editingSectionId,
    setEditingSectionId,
    editBuffer,
    setEditBuffer,
    handleSaveSection,
    sectionLocks,
    handleToggleSectionLock,
  } = state;

  // The section text the current edit STARTED from. Sent back as
  // `base_content` so the server can three-way merge the save onto the
  // latest stored section ("last version + this edit").
  const editBaseRef = useRef<string>('');

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Styled markdown content rendering */}
      <article className="bg-white p-6 md:p-10 rounded-3xl border border-outline shadow-sm prose prose-neutral max-w-none">
        
        {/* Header decorative accent */}
        <div className="h-1 w-24 bg-primary mb-6 rounded-full no-print"></div>
        
        {!prdMarkdown ? (
          <div className="flex flex-col items-center justify-center py-20 text-center text-on-surface-variant no-print">
            <FileText className="w-12 h-12 text-primary/40 mb-4 animate-pulse" />
            <p className="font-bold text-lg text-on-surface">PRD template not loaded yet</p>
            <p className="text-xs max-w-sm mt-1">The Krungsri Nimble template could not be fetched. Enter your raw requirements in the chat or click Generate PRD to build the document.</p>
          </div>
        ) : (
          <div className="space-y-10 divide-y divide-slate-100">
            {sections.map((section, sectionIdx) => {
              const isEditing = editingSectionId === section.id;
              const safeTitle = getSafeSectionTitle(section.title);
              const safeContent = getSafeSectionContent(section.content);
              
              return (
                <div 
                  key={section.id} 
                  className={`relative group pt-8 first:pt-0 transition-all duration-200 ${
                    isEditing 
                      ? 'bg-slate-50/50 p-6 rounded-2xl border border-primary/20 shadow-sm' 
                      : 'border-transparent hover:bg-slate-50/20 px-2 rounded-2xl'
                  }`}
                >
                  {/* Header Area with Title & Edit button */}
                  <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 mb-5">
                    <h3 className="text-xs font-bold font-mono text-primary uppercase tracking-wider flex items-center gap-2">
                      <span className="opacity-40 font-semibold text-[10px]">#0{sectionIdx + 1}</span>
                      <span>{safeTitle}</span>
                    </h3>
                    
                    <div className="flex items-center gap-2">
                      {/* Per-part ownership + review badges */}
                      {(() => {
                        const lock = sectionLocks[section.id];
                        if (!lock) return null;
                        const sourceLabel =
                          lock.content_source === 'human' ? 'Manual'
                          : lock.content_source === 'template' ? 'Template'
                          : 'AI';
                        const sourceClass =
                          lock.content_source === 'human' ? 'bg-violet-100 text-violet-700 border-violet-200'
                          : lock.content_source === 'template' ? 'bg-slate-100 text-slate-600 border-slate-200'
                          : 'bg-sky-100 text-sky-700 border-sky-200';
                        const satisfied = lock.review_status === 'satisfied' || lock.review_status === 'approved';
                        return (
                          <>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide ${sourceClass}`}>
                              {sourceLabel}
                            </span>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide ${
                              satisfied
                                ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                                : 'bg-slate-100 text-slate-500 border-slate-200'
                            }`}>
                              {satisfied ? 'Satisfied' : 'Draft'}
                            </span>
                          </>
                        );
                      })()}

                      {/* Lock/Unlock button for this part */}
                      {(() => {
                        const isLocked = sectionLocks[section.id]?.is_locked ?? false;
                        return (
                          <button
                            onClick={() => handleToggleSectionLock(section.id)}
                            title={
                              isLocked
                                ? 'This part is locked — edits and AI regeneration are blocked.'
                                : 'Lock this part — the Architect will never overwrite it again.'
                            }
                            className={`opacity-60 hover:opacity-100 group-hover:opacity-100 transition-opacity text-[11px] px-2.5 py-1.5 rounded-xl flex items-center gap-1.5 border shadow-sm cursor-pointer z-10 font-semibold ${
                              isLocked
                                ? 'bg-amber-100 text-amber-800 border-amber-300 hover:bg-amber-200'
                                : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
                            }`}
                          >
                            {isLocked ? (
                              <>
                                <Unlock className="w-3.5 h-3.5 text-amber-700" />
                                <span>Unlock</span>
                              </>
                            ) : (
                              <>
                                <Lock className="w-3.5 h-3.5 text-primary" />
                                <span>Lock</span>
                              </>
                            )}
                          </button>
                        );
                      })()}

                      {!isEditing && (
                        <button
                          onClick={() => {
                            setEditingSectionId(section.id);
                            setEditBuffer(safeContent);
                            editBaseRef.current = safeContent;
                          }}
                          disabled={sectionLocks[section.id]?.is_locked ?? false}
                          className={`opacity-60 hover:opacity-100 group-hover:opacity-100 transition-opacity bg-white hover:bg-slate-50 text-slate-700 text-[11px] px-2.5 py-1.5 rounded-xl flex items-center gap-1.5 border border-slate-200 shadow-sm cursor-pointer z-10 font-semibold disabled:opacity-30 disabled:cursor-not-allowed`}
                        >
                          <Pencil className="w-3.5 h-3.5 text-primary" />
                          <span>Edit</span>
                        </button>
                      )}
                    </div>
                  </div>
{isEditing ? (
                    <div className="space-y-4">
                      <textarea
                        ref={(el) => {
                          if (el) {
                            el.style.height = 'auto';
                            el.style.height = `${el.scrollHeight}px`;
                          }
                        }}
                        value={editBuffer}
                        onChange={(e) => {
                          setEditBuffer(e.target.value);
                          e.target.style.height = 'auto';
                          e.target.style.height = `${e.target.scrollHeight}px`;
                        }}
                        className="w-full text-sm font-sans text-slate-800 bg-white border border-slate-200 rounded-2xl p-4.5 focus:ring-2 focus:ring-primary/20 focus:border-primary outline-none transition-all resize-y custom-scrollbar shadow-inner min-h-[120px]"
                        placeholder="Enter section content in markdown..."
                      />
                      <div className="flex items-center justify-between pt-3 border-t border-slate-100 mt-2">
                        <p className="text-[11px] text-slate-500 italic">
                          Saved & versioned per part — lock an approved part and the Architect will never overwrite it.
                        </p>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => {
                              setEditingSectionId(null);
                              setEditBuffer("");
                            }}
                            className="px-3.5 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold shadow-sm transition-all cursor-pointer"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handleSaveSection(section.id, editBuffer, editBaseRef.current)}
                            className="px-4 py-1.5 rounded-xl bg-primary text-on-primary hover:brightness-110 text-xs font-semibold shadow-md transition-all flex items-center gap-1.5 cursor-pointer"
                          >
                            <Save className="w-3.5 h-3.5" />
                            <span>Save Changes</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="prose prose-slate max-w-none pb-4">
                      {parseAndRenderMarkdown(safeContent)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </article>
    </div>
  );
}